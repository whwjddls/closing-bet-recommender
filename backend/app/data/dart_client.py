from __future__ import annotations

import datetime as dt
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, MutableMapping

logger = logging.getLogger(__name__)

# 희석 화이트리스트(아키텍처 §2 재 veto) → veto=0(차단). substring 매칭(정정 변형 포착)
DILUTION_WHITELIST: tuple[str, ...] = (
    "유상증자결정",
    "전환사채권발행결정",
    "신주인수권부사채권발행결정",
    "교환사채권발행결정",
)
# non-dilutive(false-veto 금지) — 무상증자/주식배당은 절대 차단 안 함
NON_DILUTIVE_EXCLUDED: tuple[str, ...] = ("무상증자결정", "주식배당")

VETO_BLOCK = 0   # 매수 차단(희석/확인불가 fail-closed)
VETO_CLEAR = 1   # 통과

Transport = Callable[[dict], dict | None]
CorpDocFetcher = Callable[[], str]


@dataclass(slots=True)
class Disclosure:
    corp_code: str
    report_nm: str
    rcept_dt: str  # YYYYMMDD


# /disclosures 위젯: 최근 희석/배당 관련 공시 분류표(카테고리 → report_nm substring)
DISCLOSURE_KINDS: dict[str, tuple[str, ...]] = {
    "희석": (
        "유상증자결정",
        "전환사채권발행결정",
        "신주인수권부사채권발행결정",
        "교환사채권발행결정",
    ),
    "배당": (
        "현금ㆍ현물배당결정",
        "현금배당결정",
        "주식배당",
        "배당",
        "권리락",
    ),
}
DART_LIST_PAGE_COUNT = 100          # DART list.json 페이지당 최대 건수


def _total_page(payload: dict) -> int:
    """list.json total_page 관대 파싱(부재/이형 → 1페이지)."""
    try:
        return max(1, int(payload.get("total_page")))
    except (TypeError, ValueError):
        return 1


def _classify_disclosure(report_nm: str,
                         kinds: dict[str, tuple[str, ...]]) -> str | None:
    """report_nm 을 kinds 카테고리로 분류. 첫 매칭 카테고리 반환, 무관 시 None.
       substring 매칭 → '유상증자결정(정정)' 등 정정 변형도 포착."""
    for category, keywords in kinds.items():
        if any(key in report_nm for key in keywords):
            return category
    return None


def parse_corp_code_xml(xml_text: str) -> list[tuple[str, str, str]]:
    """DART corpCode.xml → [(corp_code, ticker, name)] (상장 종목코드 보유분만)."""
    root = ET.fromstring(xml_text)
    out: list[tuple[str, str, str]] = []
    for item in root.findall("list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        name = (item.findtext("corp_name") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if corp_code and stock_code:               # 비상장(종목코드 공란) 제외
            out.append((corp_code, stock_code, name))
    return out


class DartClient:
    """VETO 소스. transport/corp_code_map/corp_doc_fetcher 주입 → 네트워크 없는 테스트."""

    def __init__(self, transport: Transport,
                 corp_code_map: MutableMapping[str, str], *,
                 api_key: str = "", corp_doc_fetcher: CorpDocFetcher | None = None):
        self._transport = transport
        self._map = corp_code_map
        self._api_key = api_key
        self._corp_doc_fetcher = corp_doc_fetcher

    def resolve_corp_code(self, ticker: str) -> str | None:
        return self._map.get(ticker)

    def fetch_disclosures(self, corp_code: str, bgn_de: str,
                          end_de: str) -> list[Disclosure] | None:
        """None = 조회 실패(fail-closed 신호), [] = 공시 없음."""
        try:
            payload = self._transport({
                "crtfc_key": self._api_key, "corp_code": corp_code,
                "bgn_de": bgn_de, "end_de": end_de})
        except Exception:
            return None
        if not payload:
            return None
        status = payload.get("status")
        if status == "013":          # 조회된 데이터 없음
            return []
        if status != "000":          # 비정상 → fail-closed
            return None
        return [Disclosure(it.get("corp_code", ""), it.get("report_nm", ""),
                           it.get("rcept_dt", ""))
                for it in payload.get("list", [])]

    @staticmethod
    def _is_dilutive(report_nm: str) -> bool:
        # 무상증자/주식배당 false-veto 금지(우선 배제)
        if any(x in report_nm for x in NON_DILUTIVE_EXCLUDED):
            return False
        # substring 매칭 → "유상증자결정(정정)" 등 정정 변형도 포착
        return any(key in report_nm for key in DILUTION_WHITELIST)

    def dilution_veto(self, ticker: str, snapshot_at: dt.datetime) -> int:
        """라이브 veto. 윈도우 T-1 15:20 ~ snapshot_at(=T 15:20) 확정 공시만.
           corp_code 미매핑 → 0(fail-closed). 시각 불가 → 당일(T) 공시는 라이브 veto
           제외(룩어헤드 방지, 익일 overnight_scan으로만 플래그)."""
        corp_code = self.resolve_corp_code(ticker)
        if not corp_code:                       # 미매핑 → fail-closed
            return VETO_BLOCK
        snapshot_date = snapshot_at.date()
        bgn_de = (snapshot_date - dt.timedelta(days=1)).strftime("%Y%m%d")  # T-1
        end_de = snapshot_date.strftime("%Y%m%d")                          # T
        disclosures = self.fetch_disclosures(corp_code, bgn_de, end_de)
        if disclosures is None:                 # DART down → fail-closed
            return VETO_BLOCK
        for d in disclosures:
            if not (bgn_de <= d.rcept_dt <= end_de):
                continue                        # 윈도우 밖(방어적 날짜 필터)
            if d.rcept_dt == end_de:
                continue                        # 당일(T) post-15:20 → 라이브 veto 제외
            if self._is_dilutive(d.report_nm):
                return VETO_BLOCK               # T-1 희석 공시 → 차단
        return VETO_CLEAR

    def dilution_veto_bulk(self, tickers: list[str],
                           snapshot_at: dt.datetime) -> dict[str, int]:
        """라이브 veto 벌크(15:20 임계경로) — per-ticker dilution_veto 와 완전 동치.

        corp_code 없이 list.json 을 bgn_de=T-1 로 시장 전체 조회(+페이지네이션 전 순회)해
        T-1 희석공시 stock_code 집합을 만든 뒤 종목별 veto 를 산출한다. 종목별 DART HTTP
        직렬(200종목×0.6~1.1s)을 시장 1콜(+페이지)로 대체한다.

        fail-closed 불변식: 첫 페이지 실패(예외/status!=000·013/빈 payload)나 순회 중
        어느 페이지라도 실패하면 전 종목 VETO_BLOCK(per-ticker DART무응답 계약과 동일).
        페이지네이션 필수 — T-1 희석공시가 2페이지 이후에 있어도 놓치지 않는다(놓치면
        fail-OPEN → 희석 종목 추천 머니 안전 사고). status=='013'(데이터 없음)은 정상 빈 결과."""
        t_minus_1 = (snapshot_at.date() - dt.timedelta(days=1)).strftime("%Y%m%d")
        dilutive_t1 = self._collect_dilutive_t1(t_minus_1)
        if dilutive_t1 is None:                         # 조회/페이지 실패 → 전 종목 fail-closed
            return {ticker: VETO_BLOCK for ticker in tickers}
        result: dict[str, int] = {}
        for ticker in tickers:
            if not self.resolve_corp_code(ticker):      # 미매핑 → fail-closed
                result[ticker] = VETO_BLOCK
            elif ticker in dilutive_t1:                 # T-1 희석 공시 → 차단
                result[ticker] = VETO_BLOCK
            else:
                result[ticker] = VETO_CLEAR
        return result

    def _collect_dilutive_t1(self, t_minus_1: str) -> set[str] | None:
        """list.json 을 bgn_de=t_minus_1 로 전 페이지 순회 → rcept_dt==t_minus_1 이고
           희석인 상장 stock_code 집합. 실패(fail-closed) 시 None."""
        first = self._fetch_list_page(t_minus_1, 1)
        if first is None:
            return None
        payload, dilutive = first
        for page_no in range(2, _total_page(payload) + 1):
            page = self._fetch_list_page(t_minus_1, page_no)
            if page is None:                            # 어느 페이지라도 실패 → fail-closed
                return None
            dilutive |= page[1]
        return dilutive

    def _fetch_list_page(self, bgn_de: str,
                         page_no: int) -> tuple[dict, set[str]] | None:
        """list.json 단일 페이지 조회 → (payload, 이 페이지의 T-1 희석 stock_code 집합).
           실패(예외/빈 payload/status!=000·013) → None(fail-closed).
           status=='013'(데이터 없음) → 정상 빈 결과((payload, empty))."""
        try:
            payload = self._transport({
                "crtfc_key": self._api_key, "bgn_de": bgn_de,
                "page_no": page_no, "page_count": DART_LIST_PAGE_COUNT})
        except Exception:                               # noqa: BLE001  (외부 IO → fail-closed)
            return None
        if not payload:
            return None
        status = payload.get("status")
        if status == "013":                             # 데이터 없음 → 정상 빈 결과
            return payload, set()
        if status != "000":                             # 비정상 → fail-closed
            return None
        dilutive: set[str] = set()
        for it in payload.get("list", []):
            stock_code = (it.get("stock_code") or "").strip()
            if not stock_code:                          # 비상장(종목코드 공란) 제외
                continue
            if (it.get("rcept_dt", "") == bgn_de        # T-1 확정 공시만(룩어헤드 제외)
                    and self._is_dilutive(it.get("report_nm", ""))):
                dilutive.add(stock_code)
        return payload, dilutive

    def overnight_scan(self, ticker: str, since: dt.datetime,
                       until: dt.datetime) -> bool:
        """익일 재스캔(성과 로그용). [since, until] 내 희석 공시 존재 여부(당일 T 포함).
           미매핑/조회실패 → False(기록용 fail-open, veto 아님)."""
        corp_code = self.resolve_corp_code(ticker)
        if not corp_code:
            return False
        bgn_de = since.strftime("%Y%m%d")
        end_de = until.strftime("%Y%m%d")
        disclosures = self.fetch_disclosures(corp_code, bgn_de, end_de)
        if not disclosures:
            return False
        return any(self._is_dilutive(d.report_nm)
                   for d in disclosures if bgn_de <= d.rcept_dt <= end_de)

    def recent_disclosures(self, since: str,
                           kinds: dict[str, tuple[str, ...]]) -> list[dict]:
        """[since, 오늘] DART list.json 최근 공시 중 희석/배당 관련만 분류 반환.
           kinds = {카테고리: (report_nm substring, ...)}. 상장(stock_code 보유)만.
           조회 실패/비정상 status → [](graceful, 200 유지). 네트워크는 transport 몫."""
        try:
            payload = self._transport({
                "crtfc_key": self._api_key, "bgn_de": since,
                "page_count": DART_LIST_PAGE_COUNT})
        except Exception:
            return []
        if not payload or payload.get("status") != "000":
            return []
        out: list[dict] = []
        for it in payload.get("list", []):
            ticker = (it.get("stock_code") or "").strip()
            if not ticker:                              # 비상장(종목코드 공란) 제외
                continue
            report_nm = it.get("report_nm", "")
            kind = _classify_disclosure(report_nm, kinds)
            if kind is None:                            # 희석/배당 무관 → 제외
                continue
            out.append({
                "date": it.get("rcept_dt", ""),
                "ticker": ticker,
                "name": it.get("corp_name", ""),
                "kind": kind,
                "title": report_nm,
            })
        return out

    def refresh_corp_codes(self, *, doc_fetcher: CorpDocFetcher | None = None) -> int:
        """corpCode.xml 다운로드·파싱 → corp_code_map upsert(ticker→corp_code). 건수 반환."""
        fetch = doc_fetcher or self._corp_doc_fetcher
        if fetch is None:
            return 0
        try:
            entries = parse_corp_code_xml(fetch())
        except Exception:
            return 0
        for corp_code, ticker, _name in entries:
            self._map[ticker] = corp_code
        return len(entries)


# ── 모듈 정본 인터페이스(00 §2) — 익일 재스캔 스케줄러 기본 바인딩 ──────────
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"


def _default_transport(params: dict) -> dict | None:
    import requests

    resp = requests.get(DART_LIST_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _load_corp_code_map() -> dict[str, str]:
    """운영 corp_code_map(ticker→corp_code) 을 CorpCodeMap 테이블에서 로드."""
    from sqlalchemy import select

    from app.store.db import SessionLocal
    from app.store.models import CorpCodeMap

    with SessionLocal() as db:
        rows = db.scalars(select(CorpCodeMap)).all()
        return {r.ticker: r.corp_code for r in rows if r.ticker}


def _api_key_from_env() -> str:
    import os

    value = os.environ.get("DART_API_KEY")
    if not value:
        raise RuntimeError(
            "운영 DART 크리덴셜 미설정: 환경변수 DART_API_KEY 필요(fail-closed).")
    return value


def build_default_client() -> DartClient:
    """운영 기본 DartClient — env api_key + DB corp_code_map + 실 transport 조립."""
    return DartClient(_default_transport, _load_corp_code_map(),
                      api_key=_api_key_from_env())


# ── corp_code_map 시딩(장전 스케줄러 기본 바인딩) ──────────────────────────
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"


def _default_zip_get(url: str, params: dict) -> bytes:
    import requests

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


def fetch_corp_code_xml(api_key: str, http_get=None) -> str:
    """DART corpCode.xml(ZIP 바이너리) 다운로드 → 내부 XML 텍스트.

    ``http_get(url, params) -> bytes`` 주입으로 오프라인 테스트."""
    import io
    import zipfile

    raw = (http_get or _default_zip_get)(DART_CORP_CODE_URL, {"crtfc_key": api_key})
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        return zf.read(name).decode("utf-8")


def refresh_corp_code_map(db, *, api_key: str | None = None, fetch_xml=None) -> int:
    """corpCode.xml 다운로드·파싱 → corp_code_map upsert. 갱신 후 매핑 수 반환.

    빈 corp_code_map 은 전 종목 veto=0(fail-closed) → 보드 영구 공백이므로
    premarket 이 매일 호출한다. 다운로드/파싱 실패 시 기존 맵을 보존하고
    기존 매핑 수를 반환한다 — 반환 0 만이 차단(BLOCKED) 사유."""
    from app.store.corp_codes import count_mapped, upsert_corp_code_map

    try:
        xml_text = (fetch_xml or fetch_corp_code_xml)(api_key or _api_key_from_env())
        entries = parse_corp_code_xml(xml_text)
        if entries:
            upsert_corp_code_map(db, entries)
    except Exception as exc:                        # noqa: BLE001  (외부 IO 방어)
        logger.warning("corp_code_map 갱신 실패(기존 맵 유지): %s", exc)
    return count_mapped(db)


def overnight_scan(ticker: str, since: dt.datetime, until: dt.datetime,
                   client: DartClient | None = None) -> bool:
    """모듈 정본 래퍼(익일 재스캔 스케줄러 기본 바인딩, 00 §2).

    ``scoring_job`` 이 ``from app.data.dart_client import overnight_scan`` 으로 지연
    바인딩한다. 미주입 시 env/DB 기본 클라이언트로 위임."""
    return (client or build_default_client()).overnight_scan(ticker, since, until)


def recent_disclosures(since: str, kinds: dict[str, tuple[str, ...]] | None = None,
                       client: DartClient | None = None) -> list[dict]:
    """모듈 정본 래퍼(/disclosures 위젯). ``since`` 이후 희석/배당 관련 공시 파싱 리스트.
       기본 클라이언트 조립 실패(크리덴셜 미설정 등) 시 [](graceful, 200 유지)."""
    kinds = kinds if kinds is not None else DISCLOSURE_KINDS
    try:
        active = client or build_default_client()
    except Exception:
        return []
    return active.recent_disclosures(since, kinds)
