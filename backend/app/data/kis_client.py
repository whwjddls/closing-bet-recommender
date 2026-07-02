from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from app.data.broker_adapter import IndexLevel, ValueRankEntry
from app.data.mapping import Market, kis_index_code, normalize_ticker

TR_VALUE_RANKING = "FHPST01710000"
TR_QUOTE = "FHKST01010100"
TR_INDEX = "FHPUP02100000"
TR_MINUTE = "FHKST03010200"          # 분봉(09:00–10:00 VWAP)
TR_NEAR_NEW_HIGH = "FHPST01870000"   # 신고가 근접(near-new-highlow)
TR_VI_STATUS = "FHPST01390000"       # VI 발동 종목
TR_LIMIT_UP = "FHKST130000C0"        # 상한가 포착(capture-uplowprice)
TR_EXP_CLOSING = "FHKST117300C0"     # 예상 체결가(exp-closing-price)
TR_PROVISIONAL_FLOW = "FHPTJ04400000"  # 외인·기관 당일 가집계(foreign-institution-total)
TR_STOCK_INFO = "CTPF1002R"          # 종목 기본정보(search-stock-info)
TR_HOLIDAY = "CTCA0903R"             # 국내휴장일조회(chk-holiday)
TR_NEWS_TITLE = "FHKST01011800"      # 종합 시황/공시(제목)(news-title)
NEWS_MAX_ITEMS = 10
TOKEN_PATH = "/oauth2/tokenP"

# 응답 목 기반 유연 파싱용 종목코드 후보 키(TR마다 mksc_/stck_ 혼재)
_TICKER_KEYS = ("mksc_shrn_iscd", "stck_shrn_iscd")
OVERHEAT_PCT = 20.0
LIMIT_UP_PCT = 29.5                  # 상한가 best-effort 임계(±30% 근접)
RANKING_TOP_N = 30

Transport = Callable[..., dict]


@dataclass(slots=True)
class Quote:
    """00 §2 정본 — 과열가드 플래그(is_halted/is_limit_up/is_vi) 포함(폴백 아님, 항상 존재)."""
    ticker: str
    price: float
    cum_volume: int
    change_pct: float
    is_halted: bool = False
    is_limit_up: bool = False
    is_vi: bool = False


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


@dataclass(slots=True, frozen=True)
class KisConfig:
    app_key: str
    app_secret: str
    base_url: str
    account: str


class KisClient:
    """PROVISIONAL 소스. transport/clock 주입 → 네트워크·실시간 없는 테스트."""

    def __init__(self, transport: Transport, clock: Clock, config: KisConfig,
                 *, rate_per_sec: int = 20, expiry_skew: float = 60.0,
                 issue_throttle: float = 60.0, token_cache: Path | None = None):
        self._transport = transport
        self._clock = clock
        self._cfg = config
        self._min_interval = 1.0 / rate_per_sec
        self._expiry_skew = expiry_skew
        self._issue_throttle = issue_throttle
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._last_issue_ts: float | None = None
        self._last_call_ts: float | None = None
        # 파일 공유 토큰 캐시 — KIS 접근토큰 발급은 1분 1회 제한. 요청/프로세스마다 새
        # 인스턴스가 각자 발급하면 403 → 토큰(24h)을 파일로 공유해 발급을 하루 ~1회로.
        self._token_cache = token_cache

    # ── 토큰 파일 캐시 ────────────────────────────────────
    def _cache_key(self) -> str:
        return f"{self._cfg.app_key}:{self._cfg.base_url}"

    def _read_token_cache(self) -> tuple[str, float] | None:
        if self._token_cache is None or not self._token_cache.exists():
            return None
        try:
            data = json.loads(self._token_cache.read_text(encoding="utf-8"))
            if data.get("key") != self._cache_key():
                return None                          # 다른 계정/서버 토큰 오용 방지
            return str(data["access_token"]), float(data["expiry_ts"])
        except Exception:                            # noqa: BLE001  (손상 파일 → 무시)
            return None

    def _write_token_cache(self, token: str, expiry_ts: float) -> None:
        if self._token_cache is None:
            return
        try:
            self._token_cache.parent.mkdir(parents=True, exist_ok=True)
            self._token_cache.write_text(json.dumps(
                {"access_token": token, "expiry_ts": expiry_ts,
                 "key": self._cache_key()}), encoding="utf-8")
        except Exception:                            # noqa: BLE001  (캐시 실패는 비치명)
            pass

    # ── 토큰 ──────────────────────────────────────────────
    def _ensure_token(self) -> str:
        now = self._clock.now()
        if self._token and now < self._token_expiry - self._expiry_skew:
            return self._token
        cached = self._read_token_cache()            # 파일 공유 토큰(타 인스턴스 발급분)
        if cached and now < cached[1] - self._expiry_skew:
            self._token, self._token_expiry = cached
            return self._token
        if (self._token and self._last_issue_ts is not None
                and (now - self._last_issue_ts) < self._issue_throttle):
            return self._token  # 재발급 throttle: stale 재사용
        try:
            resp = self._transport(
                "POST", f"{self._cfg.base_url}{TOKEN_PATH}",
                headers={"content-type": "application/json"},
                json={"grant_type": "client_credentials",
                      "appkey": self._cfg.app_key,
                      "appsecret": self._cfg.app_secret})
        except Exception:
            # 발급 실패(예: 1분 1회 403) — 만료 전 캐시가 있으면 그걸로 동작(fail-soft)
            if cached and now < cached[1]:
                self._token, self._token_expiry = cached
                return self._token
            if self._token and now < self._token_expiry:
                return self._token
            raise
        self._token = resp["access_token"]
        self._token_expiry = now + float(resp["expires_in"])
        self._last_issue_ts = now
        self._write_token_cache(self._token, self._token_expiry)
        return self._token

    # ── 레이트버짓 ────────────────────────────────────────
    def _pace(self) -> None:
        now = self._clock.now()
        if self._last_call_ts is not None:
            wait = self._min_interval - (now - self._last_call_ts)
            if wait > 0:
                self._clock.sleep(wait)
        self._last_call_ts = self._clock.now()

    def _tr_request(self, tr_id: str, path: str, params: dict) -> dict:
        token = self._ensure_token()
        self._pace()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._cfg.app_key,
            "appsecret": self._cfg.app_secret,
            "tr_id": tr_id,
            "content-type": "application/json",
        }
        return self._transport("GET", f"{self._cfg.base_url}{path}",
                               headers=headers, params=params)

    # ── TR 래퍼 ───────────────────────────────────────────
    def get_quote(self, ticker: str) -> Quote:
        ticker = normalize_ticker(ticker)
        resp = self._tr_request(
            TR_QUOTE, "/uapi/domestic-stock/v1/quotations/inquire-price",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker})
        out = resp.get("output", {})
        price = float(out.get("stck_prpr", 0) or 0)
        cum_volume = int(float(out.get("acml_vol", 0) or 0))
        change_pct = float(out.get("prdy_ctrt", 0) or 0)
        is_halted = str(out.get("temp_stop_yn", "N")) == "Y"
        is_limit_up = change_pct >= LIMIT_UP_PCT          # 상한가 best-effort
        # VI 전용 엔드포인트 부재 → 과열 폴백(상한가/등락률≥+20%). 필드는 항상 존재.
        is_vi = is_limit_up or change_pct >= OVERHEAT_PCT
        return Quote(ticker, price, cum_volume, change_pct,
                     is_halted=is_halted, is_limit_up=is_limit_up, is_vi=is_vi)

    def get_value_ranking(self, market: Market) -> list[ValueRankEntry]:
        # 거래대금 순위 = volume-rank(FHPST01710000) FID_BLNG_CLS_CODE="3"(거래금액순).
        resp = self._tr_request(
            TR_VALUE_RANKING,
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
             "FID_INPUT_ISCD": kis_index_code(market),
             "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "3",
             "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "000000",
             "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "",
             "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""})
        rows = resp.get("output", []) or []
        entries = []
        for row in rows[:RANKING_TOP_N]:
            entries.append(ValueRankEntry(
                ticker=normalize_ticker(row.get("mksc_shrn_iscd", "0")),
                value=float(row.get("acml_tr_pbmn", 0) or 0),
                rank=int(float(row.get("data_rank", 0) or 0))))
        return entries

    def get_index_level(self, market: Market) -> IndexLevel:
        resp = self._tr_request(
            TR_INDEX,
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            {"FID_COND_MRKT_DIV_CODE": "U",
             "FID_INPUT_ISCD": kis_index_code(market)})
        out = resp.get("output", {})
        return IndexLevel(market, float(out.get("bstp_nmix_prpr", 0) or 0))

    def fetch_morning_vwap(self, ticker: str, d: date) -> float | None:
        """익일 09:00–10:00 VWAP(분봉, TR FHKST03010200). 거래 결측 시 None."""
        ticker = normalize_ticker(ticker)
        resp = self._tr_request(
            TR_MINUTE,
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker,
             "FID_INPUT_DATE_1": d.strftime("%Y%m%d"),
             "FID_INPUT_HOUR_1": "100000"})
        rows = resp.get("output2") or resp.get("output") or []
        num = 0.0
        den = 0.0
        for row in rows:
            hhmmss = str(row.get("stck_cntg_hour", "000000"))
            if not ("090000" <= hhmmss <= "100000"):      # 09:00–10:00 윈도우만
                continue
            price = float(row.get("stck_prpr", 0) or 0)
            vol = float(row.get("cntg_vol", 0) or 0)
            num += price * vol
            den += vol
        if den == 0:
            return None                                   # 거래 결측 → None
        return num / den

    # ── 신규 TR 래퍼 5종(T3) — 모두 graceful(예외→빈 결과) ───────────────
    def get_near_new_highs(self) -> list[dict]:
        """신고가 근접 랭킹(near-new-highlow) → [{ticker, name}]. 실패 시 []."""
        try:
            resp = self._tr_request(
                TR_NEAR_NEW_HIGH,
                "/uapi/domestic-stock/v1/ranking/near-new-highlow",
                {"FID_APLY_RANG_VOL": "100", "FID_COND_MRKT_DIV_CODE": "J",
                 "FID_COND_SCR_DIV_CODE": "20187", "FID_DIV_CLS_CODE": "0",
                 "FID_INPUT_CNT_1": "0", "FID_INPUT_CNT_2": "5",
                 "FID_PRC_CLS_CODE": "0", "FID_INPUT_ISCD": "0000",
                 "FID_TRGT_CLS_CODE": "", "FID_TRGT_EXLS_CLS_CODE": "",
                 "FID_APLY_RANG_PRC_1": "", "FID_APLY_RANG_PRC_2": ""})
        except Exception:                                  # noqa: BLE001  (외부 IO — graceful)
            return []
        rows = []
        for row in resp.get("output", []) or []:
            ticker = _row_ticker(row)
            if ticker is None:
                continue
            rows.append({"ticker": ticker,
                         "name": _first(row, ("hts_kor_isnm", "prdt_name"), "")})
        return rows

    def get_vi_tickers(self) -> set[str]:
        """VI 발동 종목코드 집합. 실패 시 빈 집합."""
        try:
            resp = self._tr_request(
                TR_VI_STATUS,
                "/uapi/domestic-stock/v1/quotations/inquire-vi-status",
                {"FID_DIV_CLS_CODE": "0", "FID_COND_SCR_DIV_CODE": "20139",
                 "FID_MRKT_CLS_CODE": "0", "FID_INPUT_ISCD": "",
                 "FID_RANK_SORT_CLS_CODE": "0",
                 "FID_INPUT_DATE_1": date.today().strftime("%Y%m%d"),
                 "FID_TRGT_CLS_CODE": "", "FID_TRGT_EXLS_CLS_CODE": ""})
        except Exception:                                  # noqa: BLE001  (외부 IO — graceful)
            return set()
        return _tickers_of(resp.get("output", []) or [])

    def get_limit_up_tickers(self) -> set[str]:
        """상한가 종목코드 집합(capture-uplowprice, 상한가). 실패 시 빈 집합."""
        try:
            resp = self._tr_request(
                TR_LIMIT_UP,
                "/uapi/domestic-stock/v1/quotations/capture-uplowprice",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "11300",
                 "FID_PRC_CLS_CODE": "0", "FID_DIV_CLS_CODE": "0",
                 "FID_INPUT_ISCD": "0000"})
        except Exception:                                  # noqa: BLE001  (외부 IO — graceful)
            return set()
        return _tickers_of(resp.get("output", []) or [])

    def get_exp_closing_prices(self) -> dict[str, float]:
        """예상 체결가 랭킹 → {ticker: 예상체결가}. 리스트 밖 종목은 없음. 실패 시 {}."""
        try:
            resp = self._tr_request(
                TR_EXP_CLOSING,
                "/uapi/domestic-stock/v1/quotations/exp-closing-price",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "0000",
                 "FID_RANK_SORT_CLS_CODE": "0", "FID_COND_SCR_DIV_CODE": "11173",
                 "FID_BLNG_CLS_CODE": "0"})
        except Exception:                                  # noqa: BLE001  (외부 IO — graceful)
            return {}
        prices: dict[str, float] = {}
        for row in resp.get("output", []) or []:
            ticker = _row_ticker(row)
            if ticker is None:
                continue
            raw = _first(row, ("antc_cnpr", "exp_cntg_prpr", "stck_prpr"), None)
            if raw in (None, ""):
                continue
            try:
                prices[ticker] = float(raw)
            except (TypeError, ValueError):
                continue
        return prices

    def get_provisional_flows(self) -> dict[str, str]:
        """외인·기관 당일 가집계 → {ticker: "외인▲"/"기관▲"/"외인▲기관▲"}(잠정 라벨).

        실 응답 필드가 불확실하므로 관대하게 파싱하고, 실패/미파악 시 {} 를 반환한다."""
        try:
            resp = self._tr_request(
                TR_PROVISIONAL_FLOW,
                "/uapi/domestic-stock/v1/quotations/foreign-institution-total",
                {"FID_COND_MRKT_DIV_CODE": "V", "FID_COND_SCR_DIV_CODE": "16449",
                 "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1",
                 "FID_RANK_SORT_CLS_CODE": "0", "FID_ETC_CLS_CODE": "0"})
        except Exception:                                  # noqa: BLE001  (외부 IO — graceful)
            return {}
        flows: dict[str, str] = {}
        for row in resp.get("output", []) or []:
            ticker = _row_ticker(row)
            if ticker is None:
                continue
            foreign = _to_float(_first(row, ("frgn_ntby_qty", "frgn_ntby_tr_pbmn"), 0))
            inst = _to_float(_first(row, ("orgn_ntby_qty", "orgn_ntby_tr_pbmn"), 0))
            label = ("외인▲" if foreign > 0 else "") + ("기관▲" if inst > 0 else "")
            if label:
                flows[ticker] = label
        return flows

    def get_stock_basic_info(self, ticker: str) -> dict:
        """종목 기본정보(search-stock-info) → 관리/경고/우선주 등 부적격 플래그 파싱.

        조회 실패 시 {} 를 반환한다(호출측은 '스킵하되 로그' — fail-open 아님)."""
        ticker = normalize_ticker(ticker)
        try:
            resp = self._tr_request(
                TR_STOCK_INFO,
                "/uapi/domestic-stock/v1/quotations/search-stock-info",
                {"PRDT_TYPE_CD": "300", "PDNO": ticker})
        except Exception:                                  # noqa: BLE001  (외부 IO — graceful)
            return {}
        out = resp.get("output", {}) or {}
        name = _first(out, ("prdt_abrv_name", "prdt_name", "hts_kor_isnm"), "")
        is_managed = str(_first(out, ("admn_item_yn",), "N")).upper() == "Y"
        warn_code = str(_first(out, ("mrkt_warn_cls_code",), "00"))
        is_warning = warn_code not in ("", "00", "0")
        kind = str(_first(out, ("stck_kind_cd",), "0"))
        is_preferred = kind not in ("", "0", "00") or "우" in str(name)
        return {"ticker": ticker, "name": name, "is_managed": is_managed,
                "is_warning": is_warning, "is_preferred": is_preferred,
                "is_ineligible": bool(is_managed or is_warning or is_preferred)}

    def get_holidays(self, from_date: date) -> list[date]:
        """국내휴장일조회(chk-holiday) → opnd_yn=='N' 인 날짜 list. 실패 시 [].

        응답 output rows 는 bass_dt(YYYYMMDD) + opnd_yn('N'=휴장) 형태 —
        관대 파싱하며, 파싱 불가/네트워크 실패는 빈 리스트로 흡수(fail-open)."""
        try:
            resp = self._tr_request(
                TR_HOLIDAY,
                "/uapi/domestic-stock/v1/quotations/chk-holiday",
                {"BASS_DT": from_date.strftime("%Y%m%d"),
                 "CTX_AREA_NK": "", "CTX_AREA_FK": ""})
        except Exception:                              # noqa: BLE001  (외부 IO — graceful)
            return []
        holidays: list[date] = []
        for row in resp.get("output", []) or []:
            if str(_first(row, ("opnd_yn",), "Y")).upper() != "N":
                continue                               # 영업일(opnd_yn!=N)은 제외
            parsed = _parse_yyyymmdd(_first(row, ("bass_dt",), None))
            if parsed is not None:
                holidays.append(parsed)
        return holidays

    def get_news_titles(self, ticker: str) -> list[dict]:
        """종합 시황/공시(제목)(news-title, FHKST01011800) → [{datetime, title}].

        응답 output rows 에서 제목/날짜/시간을 관대 파싱(키 이름 후보 순회),
        최대 NEWS_MAX_ITEMS(10)건. 네트워크/파싱 실패는 빈 리스트로 흡수."""
        ticker = normalize_ticker(ticker)
        try:
            resp = self._tr_request(
                TR_NEWS_TITLE,
                "/uapi/domestic-stock/v1/quotations/news-title",
                {"FID_NEWS_OFER_ENTP_CODE": "", "FID_COND_MRKT_CLS_CODE": "",
                 "FID_INPUT_ISCD": ticker, "FID_TITL_CNTT": "",
                 "FID_INPUT_DATE_1": "", "FID_INPUT_HOUR_1": "",
                 "FID_RANK_SORT_CLS_CODE": "", "FID_INPUT_SRNO": ""})
        except Exception:                              # noqa: BLE001  (외부 IO — graceful)
            return []
        items: list[dict] = []
        for row in resp.get("output", []) or []:
            title = _first(row, ("hts_pbnt_titl_cntt", "titl", "news_titl",
                                 "titl_cntt", "cntt"), "")
            if not title:
                continue                               # 제목 없는 행은 스킵
            raw_date = _first(row, ("data_dt", "bass_dt", "stck_bsop_date",
                                    "hts_pbnt_date", "news_date"), "")
            raw_time = _first(row, ("data_tm", "hts_pbnt_hour", "news_hour",
                                    "input_hour_1"), "")
            items.append({"datetime": _format_news_datetime(raw_date, raw_time),
                          "title": str(title)})
            if len(items) >= NEWS_MAX_ITEMS:
                break
        return items


# ── 응답 목 기반 유연 파싱 헬퍼 ───────────────────────────────────────────
def _parse_yyyymmdd(raw) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return datetime.strptime(str(raw), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _format_news_datetime(raw_date, raw_time) -> str:
    """YYYYMMDD/HHMMSS 후보를 'YYYY-MM-DD HH:MM' 로 관대 포맷(결측/이형은 원문 유지)."""
    d = str(raw_date or "").strip()
    tm = str(raw_time or "").strip()
    parts: list[str] = []
    if len(d) == 8 and d.isdigit():
        parts.append(f"{d[:4]}-{d[4:6]}-{d[6:]}")
    elif d:
        parts.append(d)
    if len(tm) >= 4 and tm.isdigit():
        parts.append(f"{tm[:2]}:{tm[2:4]}")
    elif tm:
        parts.append(tm)
    return " ".join(parts)



def _first(row: dict, keys: tuple, default=None):
    """row 에서 keys 순서로 첫 존재값 반환(빈 문자열은 미존재로 취급)."""
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _row_ticker(row: dict) -> str | None:
    raw = _first(row, _TICKER_KEYS, None)
    if raw in (None, ""):
        return None
    try:
        return normalize_ticker(raw)
    except ValueError:
        return None


def _tickers_of(rows: list) -> set[str]:
    out: set[str] = set()
    for row in rows:
        ticker = _row_ticker(row)
        if ticker is not None:
            out.add(ticker)
    return out


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ── 모듈 정본 인터페이스(00 §2) — 익일 채점 스케줄러 기본 바인딩 ──────────
KIS_DEFAULT_BASE_URL = "https://openapi.koreainvestment.com:9443"


class _RealClock:
    """운영 기본 시계 — KIS 레이트버짓/토큰 만료(monotonic)."""

    def now(self) -> float:
        import time

        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        import time

        time.sleep(seconds)


def _default_transport(method: str, url: str, *, headers=None,
                       json=None, params=None) -> dict:
    import requests

    resp = requests.request(method, url, headers=headers, json=json,
                            params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _config_from_env() -> KisConfig:
    import os

    def _require(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(
                f"운영 KIS 크리덴셜 미설정: 환경변수 {name} 필요(fail-closed).")
        return value

    return KisConfig(
        app_key=_require("KIS_APP_KEY"),
        app_secret=_require("KIS_APP_SECRET"),
        base_url=os.environ.get("KIS_BASE_URL", KIS_DEFAULT_BASE_URL),
        account=_require("KIS_ACCOUNT"),
    )


def default_token_cache_path() -> Path:
    """토큰 파일 캐시 정본 경로 — 모든 KisClient 인스턴스(라우터/파이프라인/채점)가 공유."""
    from app.config import get_settings
    return get_settings().state_dir / "kis_token.json"


def build_default_client() -> KisClient:
    """운영 기본 KisClient — env 크리덴셜 + 실 transport/clock 조립(fail-closed)."""
    return KisClient(_default_transport, _RealClock(), _config_from_env(),
                     token_cache=default_token_cache_path())


def fetch_morning_vwap(ticker: str, d: date,
                       client: KisClient | None = None) -> float | None:
    """모듈 정본 래퍼(익일 채점 스케줄러 기본 바인딩, 00 §2).

    ``scoring_job`` 이 ``from app.data.kis_client import fetch_morning_vwap`` 로 지연
    바인딩한다(pykrx 모듈 정본 함수와 동일 패턴). 미주입 시 env 기본 클라이언트로 위임."""
    return (client or build_default_client()).fetch_morning_vwap(ticker, d)
