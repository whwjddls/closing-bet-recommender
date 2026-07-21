import datetime as dt

import pytest

from app.data.dart_client import (
    DISCLOSURE_KINDS,
    DartClient,
    VETO_BLOCK,
    VETO_CLEAR,
    recent_disclosures,
)


class FakeDart:
    """주입형 가짜 DART list.json transport."""

    def __init__(self, payload=None, raises=False):
        self.payload = payload
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, params):
        self.calls.append(params)
        if self.raises:
            raise ConnectionError("DART down")
        return self.payload


def _ok(items):
    return {"status": "000", "message": "정상", "list": items}


def _disc(report_nm, rcept_dt="20260629", corp="00126380"):   # 기본 T-1
    return {"corp_code": corp, "report_nm": report_nm, "rcept_dt": rcept_dt}


CMAP = {"005930": "00126380"}
SNAP = dt.datetime(2026, 6, 30, 15, 20)        # T = 2026-06-30 15:20


# ── 화이트리스트 → veto=0(차단), substring 매칭(정정 변형 포착) ───────
@pytest.mark.parametrize("report_nm", [
    "유상증자결정",
    "전환사채권발행결정",
    "신주인수권부사채권발행결정",
    "교환사채권발행결정",
    "유상증자결정(정정)",
])
def test_dilution_whitelist_vetoes(report_nm):
    dart = DartClient(FakeDart(_ok([_disc(report_nm)])), CMAP)
    assert dart.dilution_veto("005930", SNAP) == VETO_BLOCK


# ── 무상증자/주식배당 → false-veto 금지(veto=1) ───────────
@pytest.mark.parametrize("report_nm", ["무상증자결정", "주식배당"])
def test_non_dilutive_does_not_veto(report_nm):
    dart = DartClient(FakeDart(_ok([_disc(report_nm)])), CMAP)
    assert dart.dilution_veto("005930", SNAP) == VETO_CLEAR


# ── corp_code 미매핑 → fail-closed(veto=0) ────────────────
def test_unmapped_corp_code_is_fail_closed():
    dart = DartClient(FakeDart(_ok([])), corp_code_map={})  # 매핑 없음
    assert dart.dilution_veto("999999", SNAP) == VETO_BLOCK


# ── DART down → fail-closed(veto=0) ───────────────────────
def test_dart_down_is_fail_closed():
    dart = DartClient(FakeDart(raises=True), CMAP)
    assert dart.dilution_veto("005930", SNAP) == VETO_BLOCK


# ── 데이터 없음(status 013) → veto=1 ──────────────────────
def test_no_disclosures_clears_veto():
    dart = DartClient(FakeDart({"status": "013", "message": "없음"}), CMAP)
    assert dart.dilution_veto("005930", SNAP) == VETO_CLEAR


# ── 윈도우 밖 공시는 무시(방어적 날짜 필터) ───────────────
def test_disclosure_outside_window_is_ignored():
    dart = DartClient(
        FakeDart(_ok([_disc("유상증자결정", rcept_dt="20260601")])), CMAP)
    # 윈도우 [20260629, 20260630] 밖 → 차단 안 함
    assert dart.dilution_veto("005930", SNAP) == VETO_CLEAR


# ── 정상 응답이지만 무관 공시만 → veto=1 ──────────────────
def test_irrelevant_disclosure_clears_veto():
    dart = DartClient(FakeDart(_ok([_disc("분기보고서")])), CMAP)
    assert dart.dilution_veto("005930", SNAP) == VETO_CLEAR


# ── 룩어헤드: 당일(T) post-15:20 공시는 라이브 veto 제외 ───
def test_same_day_disclosure_excluded_from_live_veto():
    dart = DartClient(
        FakeDart(_ok([_disc("유상증자결정", rcept_dt="20260630")])), CMAP)
    # T(20260630) 공시 → 라이브 veto 제외(익일 overnight_scan 몫)
    assert dart.dilution_veto("005930", SNAP) == VETO_CLEAR


# ── overnight_scan: 익일 재스캔(당일 T 공시 포함) → True ───
def test_overnight_scan_flags_dilutive():
    dart = DartClient(
        FakeDart(_ok([_disc("유상증자결정", rcept_dt="20260630")])), CMAP)
    since = dt.datetime(2026, 6, 30, 15, 20)
    until = dt.datetime(2026, 7, 1, 9, 0)
    assert dart.overnight_scan("005930", since, until) is True


def test_overnight_scan_false_when_no_dilution():
    dart = DartClient(
        FakeDart(_ok([_disc("분기보고서", rcept_dt="20260630")])), CMAP)
    since = dt.datetime(2026, 6, 30, 15, 20)
    until = dt.datetime(2026, 7, 1, 9, 0)
    assert dart.overnight_scan("005930", since, until) is False


# ── refresh_corp_codes: corpCode.xml 파싱·upsert(상장분만) ─
CORP_XML = """<result>
  <list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code><modify_date>20260101</modify_date></list>
  <list><corp_code>00164779</corp_code><corp_name>SK하이닉스</corp_name><stock_code>000660</stock_code><modify_date>20260101</modify_date></list>
  <list><corp_code>00999999</corp_code><corp_name>비상장법인</corp_name><stock_code></stock_code><modify_date>20260101</modify_date></list>
</result>"""


def test_refresh_corp_codes_parses_and_upserts():
    mapping: dict[str, str] = {}
    dart = DartClient(FakeDart(_ok([])), mapping)
    n = dart.refresh_corp_codes(doc_fetcher=lambda: CORP_XML)
    assert n == 2                               # 상장 2건(비상장 종목코드 공란 제외)
    assert mapping["005930"] == "00126380"
    assert mapping["000660"] == "00164779"


# ── recent_disclosures: 희석/배당 분류·상장 필터·graceful ──
def _item(report_nm, stock_code="005930", corp_name="삼성전자",
          rcept_dt="20260629", corp="00126380"):
    return {"corp_code": corp, "corp_name": corp_name, "stock_code": stock_code,
            "report_nm": report_nm, "rcept_dt": rcept_dt}


def test_recent_disclosures_classifies_dilution_and_dividend():
    payload = _ok([
        _item("유상증자결정"),
        _item("현금배당결정", stock_code="000660", corp_name="SK하이닉스"),
        _item("전환사채권발행결정(정정)", stock_code="035720", corp_name="카카오"),
        _item("분기보고서"),                    # 무관 → 제외
    ])
    dart = DartClient(FakeDart(payload), CMAP, api_key="K")
    rows = dart.recent_disclosures("20260620", DISCLOSURE_KINDS)
    assert len(rows) == 3
    assert rows[0] == {"date": "20260629", "ticker": "005930", "name": "삼성전자",
                       "kind": "희석", "title": "유상증자결정"}
    assert rows[1]["kind"] == "배당"
    assert rows[2]["kind"] == "희석"            # 정정 변형도 substring 포착


def test_recent_disclosures_skips_non_listed():
    payload = _ok([_item("유상증자결정", stock_code="")])  # 비상장(종목코드 공란)
    dart = DartClient(FakeDart(payload), CMAP, api_key="K")
    assert dart.recent_disclosures("20260620", DISCLOSURE_KINDS) == []


def test_recent_disclosures_empty_on_transport_error():
    dart = DartClient(FakeDart(raises=True), CMAP, api_key="K")
    assert dart.recent_disclosures("20260620", DISCLOSURE_KINDS) == []


def test_recent_disclosures_empty_on_error_status():
    dart = DartClient(FakeDart({"status": "010", "message": "미등록 키"}), CMAP,
                      api_key="K")
    assert dart.recent_disclosures("20260620", DISCLOSURE_KINDS) == []


def test_recent_disclosures_passes_since_and_page_count():
    fake = FakeDart(_ok([]))
    dart = DartClient(fake, CMAP, api_key="K")
    dart.recent_disclosures("20260620", DISCLOSURE_KINDS)
    assert fake.calls[-1]["bgn_de"] == "20260620"
    assert fake.calls[-1]["page_count"] == 100
    assert fake.calls[-1]["crtfc_key"] == "K"


def test_module_recent_disclosures_delegates_to_injected_client():
    dart = DartClient(FakeDart(_ok([_item("주식배당")])), CMAP, api_key="K")
    rows = recent_disclosures("20260620", client=dart)      # 기본 kinds 사용
    assert rows[0]["kind"] == "배당"
    assert rows[0]["title"] == "주식배당"


# ── corp_code_map 시딩(corpCode.xml → upsert) ────────────────────────────
SAMPLE_CORP_XML = """<result>
  <list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list>
  <list><corp_code>00164742</corp_code><corp_name>현대자동차</corp_name><stock_code>005380</stock_code></list>
  <list><corp_code>99999999</corp_code><corp_name>비상장사</corp_name><stock_code> </stock_code></list>
</result>"""


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.store.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def test_fetch_corp_code_xml_unzips_inner_xml():
    import io
    import zipfile

    from app.data.dart_client import DART_CORP_CODE_URL, fetch_corp_code_xml

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", SAMPLE_CORP_XML)
    calls = []

    def http_get(url, params):
        calls.append((url, params))
        return buf.getvalue()

    xml_text = fetch_corp_code_xml("K", http_get=http_get)
    assert "00126380" in xml_text
    assert calls == [(DART_CORP_CODE_URL, {"crtfc_key": "K"})]


def test_refresh_corp_code_map_upserts_listed_only(db_session):
    from app.data.dart_client import refresh_corp_code_map
    from app.store.models import CorpCodeMap

    mapped = refresh_corp_code_map(db_session, api_key="K",
                                   fetch_xml=lambda key: SAMPLE_CORP_XML)
    assert mapped == 2                                 # 비상장(종목코드 공란) 제외
    row = db_session.get(CorpCodeMap, "00126380")
    assert row.ticker == "005930" and row.name == "삼성전자"
    assert row.updated_at is not None

    # 멱등: 재실행해도 매핑 수 불변(merge-upsert)
    assert refresh_corp_code_map(db_session, api_key="K",
                                 fetch_xml=lambda key: SAMPLE_CORP_XML) == 2


def test_refresh_corp_code_map_failure_preserves_existing(db_session):
    # 다운로드 실패 시 기존 맵 보존 — 반환 = 기존 매핑 수(축소 금지, 0 만 차단 사유)
    from app.data.dart_client import refresh_corp_code_map
    from app.store.models import CorpCodeMap

    db_session.add(CorpCodeMap(corp_code="00126380", ticker="005930", name="삼성전자"))
    db_session.commit()

    def boom(key):
        raise ConnectionError("DART down")

    assert refresh_corp_code_map(db_session, api_key="K", fetch_xml=boom) == 1


def test_refresh_corp_code_map_empty_db_and_failure_returns_zero(db_session):
    from app.data.dart_client import refresh_corp_code_map

    def boom(key):
        raise ConnectionError("DART down")

    assert refresh_corp_code_map(db_session, api_key="K", fetch_xml=boom) == 0


# ── Part A: dilution_veto_bulk (벌크 veto — fail-closed 정확 보존 + 페이지네이션) ──
CMAP_BULK = {"005930": "00126380", "000660": "00164779", "035720": "00258801"}


def _litem(report_nm, stock_code, rcept_dt="20260629", corp="00000000"):
    """list.json 시장 전체 공시 항목(상장 stock_code 보유)."""
    return {"corp_code": corp, "corp_name": "", "stock_code": stock_code,
            "report_nm": report_nm, "rcept_dt": rcept_dt}


class MarketDart:
    """corp_code 지정(per-ticker)·전체조회(bulk, page_no) 양쪽을 같은 공시DB로 응답.

    per-ticker fetch_disclosures 는 corp_code 로 필터하고, bulk 는 page_no 페이지네이션 —
    동일 공시DB 위에서 두 경로의 veto 동치를 검증하기 위한 fake."""

    def __init__(self, disclosures, *, page_size=100):
        self.disclosures = disclosures
        self.page_size = page_size
        self.calls: list[dict] = []

    def __call__(self, params):
        self.calls.append(params)
        if "corp_code" in params:                       # per-ticker 경로(corp 필터)
            items = [d for d in self.disclosures
                     if d["corp_code"] == params["corp_code"]]
            return {"status": "000", "list": items}
        size = self.page_size                            # bulk 경로(전체 시장 페이지네이션)
        total_page = max(1, (len(self.disclosures) + size - 1) // size)
        start = (int(params["page_no"]) - 1) * size
        return {"status": "000", "total_page": total_page,
                "list": self.disclosures[start:start + size]}


def test_bulk_veto_equivalent_to_per_ticker():
    # 미매핑=0, T-1 희석=0, clear=1, 당일(T) 공시=1 혼합 → per-ticker 와 완전 동치
    discs = [
        _litem("유상증자결정", "005930", corp="00126380"),         # T-1 희석 → 0
        _litem("분기보고서", "000660", corp="00164779"),           # T-1 무관 → 1
        _litem("유상증자결정", "035720", rcept_dt="20260630",
               corp="00258801"),                                    # 당일 T → 1(룩어헤드 제외)
    ]
    tickers = ["005930", "000660", "035720", "999999"]  # 999999 미매핑 → 0
    dart = DartClient(MarketDart(discs), CMAP_BULK)
    per_ticker = {t: dart.dilution_veto(t, SNAP) for t in tickers}
    bulk = dart.dilution_veto_bulk(tickers, SNAP)
    assert bulk == per_ticker
    assert bulk == {"005930": VETO_BLOCK, "000660": VETO_CLEAR,
                    "035720": VETO_CLEAR, "999999": VETO_BLOCK}


def test_bulk_request_shape_uses_bgn_de_and_pagination_params():
    fake = MarketDart([])
    dart = DartClient(fake, CMAP_BULK, api_key="K")
    dart.dilution_veto_bulk(["005930"], SNAP)
    call = fake.calls[-1]
    assert call["crtfc_key"] == "K"
    assert call["bgn_de"] == "20260629"                 # T-1(snapshot_date - 1일)
    assert call["page_no"] == 1
    assert call["page_count"] == 100


def test_bulk_fail_closed_on_transport_error():
    dart = DartClient(FakeDart(raises=True), CMAP_BULK)
    assert dart.dilution_veto_bulk(["005930", "000660"], SNAP) == {
        "005930": VETO_BLOCK, "000660": VETO_BLOCK}       # 전 종목 fail-closed


def test_bulk_fail_closed_on_error_status():
    dart = DartClient(FakeDart({"status": "010", "message": "미등록 키"}), CMAP_BULK)
    assert dart.dilution_veto_bulk(["005930", "000660"], SNAP) == {
        "005930": VETO_BLOCK, "000660": VETO_BLOCK}


class PagingDart:
    """total_page 만큼 페이지를 나눠주는 fake — T-1 희석공시가 2페이지에 있는 경우 재현."""

    def __init__(self, pages):
        self.pages = pages
        self.calls: list[dict] = []

    def __call__(self, params):
        self.calls.append(params)
        return {"status": "000", "total_page": len(self.pages),
                "list": self.pages[int(params["page_no"]) - 1]}


def test_bulk_paginates_and_does_not_miss_dilution_on_later_page():
    # T-1 희석공시가 2페이지에 있어도 놓치면 안 됨(놓치면 fail-OPEN → 희석 종목 추천 사고)
    pages = [
        [_litem("분기보고서", "000660", corp="00164779")],          # page1(희석 없음)
        [_litem("유상증자결정", "005930", corp="00126380")],        # page2(T-1 희석)
    ]
    fake = PagingDart(pages)
    res = DartClient(fake, CMAP_BULK).dilution_veto_bulk(["005930", "000660"], SNAP)
    assert res["005930"] == VETO_BLOCK                  # 2페이지 희석 포착
    assert res["000660"] == VETO_CLEAR
    assert len(fake.calls) == 2                          # 전 페이지 순회


def test_bulk_fail_closed_when_later_page_fails():
    # 페이지 순회 중 어느 페이지라도 실패 → 전 종목 fail-closed
    class HalfFailDart:
        def __init__(self):
            self.calls: list[dict] = []

        def __call__(self, params):
            self.calls.append(params)
            if int(params["page_no"]) == 1:
                return {"status": "000", "total_page": 2, "list": []}
            raise ConnectionError("page 2 down")

    dart = DartClient(HalfFailDart(), CMAP_BULK)
    assert dart.dilution_veto_bulk(["005930", "000660"], SNAP) == {
        "005930": VETO_BLOCK, "000660": VETO_BLOCK}


def test_bulk_same_day_disclosure_excluded_from_live_veto():
    # 당일(T) post-15:20 공시는 라이브 veto 유발 안 함(룩어헤드 제외 — 익일 overnight_scan 몫)
    payload = _ok([_litem("유상증자결정", "005930", rcept_dt="20260630")])
    dart = DartClient(FakeDart(payload), CMAP_BULK)
    assert dart.dilution_veto_bulk(["005930"], SNAP) == {"005930": VETO_CLEAR}


def test_bulk_status_013_clears():
    dart = DartClient(FakeDart({"status": "013", "message": "없음"}), CMAP_BULK)
    assert dart.dilution_veto_bulk(["005930"], SNAP) == {"005930": VETO_CLEAR}
