from datetime import datetime

from app.engine.signals.veto import Disclosure, compute_veto, in_window

WIN_START = datetime(2026, 6, 29, 15, 20)
WIN_END = datetime(2026, 6, 30, 15, 20)
MAP = {"000660": "00164779"}


def _d(report_nm, at, corp="00164779"):
    return Disclosure(corp_code=corp, report_nm=report_nm, received_at=at)


def test_dilution_in_window_blocks():
    discs = [_d("유상증자결정", datetime(2026, 6, 30, 10, 0))]
    assert compute_veto("000660", MAP, discs, WIN_START, WIN_END) == 0


def test_non_dilutive_bonus_issue_does_not_veto():
    # 무상증자/주식배당 = non-dilutive → false-veto 금지
    discs = [_d("무상증자결정", datetime(2026, 6, 30, 10, 0))]
    assert compute_veto("000660", MAP, discs, WIN_START, WIN_END) == 1


def test_unmapped_ticker_fail_closed():
    assert compute_veto("999999", MAP, [], WIN_START, WIN_END) == 0


def test_disclosure_after_window_is_lookahead_guarded():
    # post-15:20 당일 공시(오버나잇 폭탄)는 윈도우 밖 → veto 미적용(익일 재스캔 로그 대상)
    discs = [_d("전환사채권발행결정", datetime(2026, 6, 30, 15, 21))]
    assert compute_veto("000660", MAP, discs, WIN_START, WIN_END) == 1


def test_window_end_inclusive_start_exclusive():
    assert in_window(WIN_END, WIN_START, WIN_END) is True
    assert in_window(WIN_START, WIN_START, WIN_END) is False


def test_other_corp_disclosure_ignored():
    discs = [_d("유상증자결정", datetime(2026, 6, 30, 10, 0), corp="99999999")]
    assert compute_veto("000660", MAP, discs, WIN_START, WIN_END) == 1


# --- 계약(00 §2): 보고서명 substring 매칭(정정 변형 포착) ---
def test_correction_variant_substring_blocks():
    # "유상증자결정(정정)" 등 정정 변형도 화이트리스트 substring으로 포착 → veto
    discs = [_d("유상증자결정(정정)", datetime(2026, 6, 30, 10, 0))]
    assert compute_veto("000660", MAP, discs, WIN_START, WIN_END) == 0


def test_stock_dividend_is_non_dilutive():
    # 주식배당 = non-dilutive → false-veto 금지
    discs = [_d("주식배당결정", datetime(2026, 6, 30, 10, 0))]
    assert compute_veto("000660", MAP, discs, WIN_START, WIN_END) == 1
