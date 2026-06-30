from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, MutableMapping

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
