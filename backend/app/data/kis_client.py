from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Protocol

from app.data.broker_adapter import IndexLevel, ValueRankEntry
from app.data.mapping import Market, kis_index_code, normalize_ticker

TR_VALUE_RANKING = "FHPST01710000"
TR_QUOTE = "FHKST01010100"
TR_INDEX = "FHPUP02100000"
TR_MINUTE = "FHKST03010200"          # 분봉(09:00–10:00 VWAP)
TOKEN_PATH = "/oauth2/tokenP"
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
                 issue_throttle: float = 60.0):
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

    # ── 토큰 ──────────────────────────────────────────────
    def _ensure_token(self) -> str:
        now = self._clock.now()
        if self._token and now < self._token_expiry - self._expiry_skew:
            return self._token
        if (self._token and self._last_issue_ts is not None
                and (now - self._last_issue_ts) < self._issue_throttle):
            return self._token  # 재발급 throttle: stale 재사용
        resp = self._transport(
            "POST", f"{self._cfg.base_url}{TOKEN_PATH}",
            headers={"content-type": "application/json"},
            json={"grant_type": "client_credentials",
                  "appkey": self._cfg.app_key,
                  "appsecret": self._cfg.app_secret})
        self._token = resp["access_token"]
        self._token_expiry = now + float(resp["expires_in"])
        self._last_issue_ts = now
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


def build_default_client() -> KisClient:
    """운영 기본 KisClient — env 크리덴셜 + 실 transport/clock 조립(fail-closed)."""
    return KisClient(_default_transport, _RealClock(), _config_from_env())


def fetch_morning_vwap(ticker: str, d: date,
                       client: KisClient | None = None) -> float | None:
    """모듈 정본 래퍼(익일 채점 스케줄러 기본 바인딩, 00 §2).

    ``scoring_job`` 이 ``from app.data.kis_client import fetch_morning_vwap`` 로 지연
    바인딩한다(pykrx 모듈 정본 함수와 동일 패턴). 미주입 시 env 기본 클라이언트로 위임."""
    return (client or build_default_client()).fetch_morning_vwap(ticker, d)
