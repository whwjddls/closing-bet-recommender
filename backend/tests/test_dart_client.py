import datetime as dt

import pytest

from app.data.dart_client import DartClient, VETO_BLOCK, VETO_CLEAR


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
