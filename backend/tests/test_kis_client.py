import datetime as dt

import pytest

from app.data.kis_client import KisClient, KisConfig
from app.data.mapping import Market


class RecordingTransport:
    """주입형 가짜 HTTP — tr_id/headers/path 기록, 큐 응답 반환."""

    def __init__(self):
        self.calls: list[dict] = []
        self.token_responses: list[dict] = []
        self.tr_responses: dict[str, list[dict]] = {}

    def request(self, method, path, *, headers=None, params=None, json=None):
        self.calls.append({"method": method, "path": path,
                           "headers": headers or {}, "params": params,
                           "json": json})
        if path.endswith("/oauth2/tokenP"):
            return self.token_responses.pop(0)
        tr = (headers or {}).get("tr_id", "")
        return self.tr_responses[tr].pop(0)


def _cfg():
    return KisConfig(app_key="K", app_secret="S",
                     base_url="https://example", account="000-00")


def _client(transport, clock):
    return KisClient(transport=transport.request, clock=clock, config=_cfg())


def _token(expires=86400):
    return {"access_token": "TKN", "expires_in": expires, "token_type": "Bearer"}


# ── 토큰 만료기반 캐시 ─────────────────────────────────────
def test_token_cached_until_expiry_then_reissued(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token(), _token()]
    t.tr_responses["FHKST01010100"] = [{"output": {"stck_prpr": "100",
        "acml_vol": "1", "prdy_ctrt": "1.0"}} for _ in range(3)]
    c = _client(t, fake_clock)

    c.get_quote("000660")               # 1차: 토큰 발급
    c.get_quote("000660")               # 만료 전: 재사용
    token_posts = [x for x in t.calls if x["path"].endswith("/oauth2/tokenP")]
    assert len(token_posts) == 1

    fake_clock.advance(90000)           # 만료 경과(>24h)
    c.get_quote("000660")               # 재발급
    token_posts = [x for x in t.calls if x["path"].endswith("/oauth2/tokenP")]
    assert len(token_posts) == 2


def test_token_reissue_throttled_even_when_expired(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token(expires=10)]
    t.tr_responses["FHKST01010100"] = [{"output": {"stck_prpr": "100",
        "acml_vol": "1", "prdy_ctrt": "1.0"}} for _ in range(3)]
    c = KisClient(transport=t.request, clock=fake_clock, config=_cfg(),
                  issue_throttle=60.0)
    c.get_quote("000660")               # t=0 발급(만료 10s)
    fake_clock.advance(20)              # 만료됐지만 throttle(60s) 내
    c.get_quote("000660")               # 재발급 금지 → stale 재사용
    token_posts = [x for x in t.calls if x["path"].endswith("/oauth2/tokenP")]
    assert len(token_posts) == 1


# ── 레이트버짓 20req/s (min-interval 페이싱) ───────────────
def test_rate_budget_paces_at_20_per_second(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01010100"] = [{"output": {"stck_prpr": "1",
        "acml_vol": "1", "prdy_ctrt": "0.0"}} for _ in range(3)]
    c = _client(t, fake_clock)
    c.get_quote("000660"); c.get_quote("005930"); c.get_quote("000020")
    # 2회의 후속 호출 전 각각 0.05s sleep
    assert fake_clock.sleeps == [pytest.approx(0.05), pytest.approx(0.05)]


# ── TR id 헤더 + 파싱 ──────────────────────────────────────
def test_get_quote_tr_id_and_parsing(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01010100"] = [{"output": {
        "stck_prpr": "24500", "acml_vol": "1234567", "prdy_ctrt": "5.20"}}]
    q = _client(t, fake_clock).get_quote("000660")
    last = t.calls[-1]
    assert last["headers"]["tr_id"] == "FHKST01010100"
    assert q.price == 24500.0
    assert q.cum_volume == 1234567
    assert q.change_pct == 5.20
    assert q.is_halted is False
    assert q.is_limit_up is False
    assert q.is_vi is False


def test_get_quote_is_vi_when_change_ge_20(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01010100"] = [{"output": {
        "stck_prpr": "100", "acml_vol": "1", "prdy_ctrt": "21.5"}}]
    q = _client(t, fake_clock).get_quote("000660")
    assert q.is_vi is True          # 과열가드 폴백: 등락률 ≥ +20%
    assert q.is_limit_up is False   # +20%대는 상한가 아님


def test_get_quote_limit_up_and_halted_flags(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01010100"] = [{"output": {
        "stck_prpr": "100", "acml_vol": "1", "prdy_ctrt": "29.91",
        "temp_stop_yn": "Y"}}]
    q = _client(t, fake_clock).get_quote("000660")
    assert q.is_halted is True
    assert q.is_limit_up is True
    assert q.is_vi is True          # 상한가 → 과열 폴백


def test_fetch_morning_vwap_filters_0900_1000_and_weights(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [{"output2": [
        {"stck_cntg_hour": "090100", "stck_prpr": "100", "cntg_vol": "10"},
        {"stck_cntg_hour": "095900", "stck_prpr": "110", "cntg_vol": "30"},
        {"stck_cntg_hour": "101500", "stck_prpr": "999", "cntg_vol": "100"},  # 윈도우 밖
    ]}]
    vwap = _client(t, fake_clock).fetch_morning_vwap("000660", dt.date(2026, 7, 1))
    assert t.calls[-1]["headers"]["tr_id"] == "FHKST03010200"
    # (100*10 + 110*30)/40 = 4300/40 = 107.5
    assert vwap == pytest.approx(107.5)


def test_fetch_morning_vwap_returns_none_when_empty(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [{"output2": []}]
    vwap = _client(t, fake_clock).fetch_morning_vwap("000660", dt.date(2026, 7, 1))
    assert vwap is None


def test_value_ranking_tr_id_and_parsing(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01710000"] = [{"output": [
        {"mksc_shrn_iscd": "000660", "acml_tr_pbmn": "1000", "data_rank": "1"},
        {"mksc_shrn_iscd": "005930", "acml_tr_pbmn": "900", "data_rank": "2"}]}]
    entries = _client(t, fake_clock).get_value_ranking(Market.KOSPI)
    assert t.calls[-1]["headers"]["tr_id"] == "FHPST01710000"
    assert entries[0].ticker == "000660"
    assert entries[0].value == 1000.0
    assert entries[0].rank == 1


def test_index_level_tr_id_and_parsing(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPUP02100000"] = [{"output": {"bstp_nmix_prpr": "2650.50"}}]
    lvl = _client(t, fake_clock).get_index_level(Market.KOSDAQ)
    assert t.calls[-1]["headers"]["tr_id"] == "FHPUP02100000"
    assert lvl.market == Market.KOSDAQ
    assert lvl.level == 2650.50


# ── 신규 TR 래퍼 5종 (T3) ─────────────────────────────────
def test_get_near_new_highs_tr_id_and_flexible_ticker_keys(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01870000"] = [{"output": [
        {"mksc_shrn_iscd": "000660", "hts_kor_isnm": "SK하이닉스"},
        {"stck_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자"}]}]
    rows = _client(t, fake_clock).get_near_new_highs()
    assert t.calls[-1]["headers"]["tr_id"] == "FHPST01870000"
    assert rows == [{"ticker": "000660", "name": "SK하이닉스"},
                    {"ticker": "005930", "name": "삼성전자"}]


def test_get_near_new_highs_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01870000"] = []            # pop → IndexError → graceful []
    assert _client(t, fake_clock).get_near_new_highs() == []


def test_get_vi_tickers_returns_set(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01390000"] = [{"output": [
        {"mksc_shrn_iscd": "000660"}, {"stck_shrn_iscd": "005930"}]}]
    vi = _client(t, fake_clock).get_vi_tickers()
    assert t.calls[-1]["headers"]["tr_id"] == "FHPST01390000"
    assert vi == {"000660", "005930"}


def test_get_vi_tickers_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01390000"] = []
    assert _client(t, fake_clock).get_vi_tickers() == set()


def test_get_limit_up_tickers_returns_set(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST130000C0"] = [{"output": [
        {"mksc_shrn_iscd": "091990"}, {"stck_shrn_iscd": "247540"}]}]
    lim = _client(t, fake_clock).get_limit_up_tickers()
    assert t.calls[-1]["headers"]["tr_id"] == "FHKST130000C0"
    assert lim == {"091990", "247540"}


def test_get_exp_closing_prices_maps_ticker_to_price(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST117300C0"] = [{"output": [
        {"mksc_shrn_iscd": "000660", "antc_cnpr": "24550"},
        {"stck_shrn_iscd": "005930", "antc_cnpr": "71200"}]}]
    prices = _client(t, fake_clock).get_exp_closing_prices()
    assert t.calls[-1]["headers"]["tr_id"] == "FHKST117300C0"
    assert prices == {"000660": 24550.0, "005930": 71200.0}


def test_get_exp_closing_prices_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST117300C0"] = []
    assert _client(t, fake_clock).get_exp_closing_prices() == {}


def test_get_provisional_flows_labels_foreign_and_institution(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPTJ04400000"] = [{"output": [
        {"mksc_shrn_iscd": "000660", "frgn_ntby_qty": "1000", "orgn_ntby_qty": "500"},
        {"stck_shrn_iscd": "005930", "frgn_ntby_qty": "2000", "orgn_ntby_qty": "-100"},
        {"mksc_shrn_iscd": "035720", "frgn_ntby_qty": "-1", "orgn_ntby_qty": "-1"}]}]
    flows = _client(t, fake_clock).get_provisional_flows()
    assert t.calls[-1]["headers"]["tr_id"] == "FHPTJ04400000"
    assert flows["000660"] == "외인▲기관▲"
    assert flows["005930"] == "외인▲"
    assert "035720" not in flows          # 순매수 없음 → 라벨 없음


def test_get_provisional_flows_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPTJ04400000"] = []
    assert _client(t, fake_clock).get_provisional_flows() == {}


def test_get_stock_basic_info_parses_flags(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": "SK하이닉스", "admn_item_yn": "N",
        "mrkt_warn_cls_code": "00", "stck_kind_cd": "0"}}]
    info = _client(t, fake_clock).get_stock_basic_info("000660")
    assert t.calls[-1]["headers"]["tr_id"] == "CTPF1002R"
    assert t.calls[-1]["params"]["PDNO"] == "000660"
    assert info["name"] == "SK하이닉스"
    assert info["is_managed"] is False
    assert info["is_ineligible"] is False


def test_get_stock_basic_info_flags_managed_ineligible(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": "관리주", "admn_item_yn": "Y"}}]
    info = _client(t, fake_clock).get_stock_basic_info("123450")
    assert info["is_managed"] is True
    assert info["is_ineligible"] is True


def test_get_stock_basic_info_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = []
    assert _client(t, fake_clock).get_stock_basic_info("000660") == {}


# ── 휴장일 조회(chk-holiday) ───────────────────────────────
def test_get_holidays_returns_opnd_n_dates(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTCA0903R"] = [{"output": [
        {"bass_dt": "20260701", "opnd_yn": "Y"},          # 영업일 → 제외
        {"bass_dt": "20260815", "opnd_yn": "N"},          # 휴장
        {"bass_dt": "20260101", "opnd_yn": "N"}]}]        # 휴장
    holidays = _client(t, fake_clock).get_holidays(dt.date(2026, 7, 1))
    last = t.calls[-1]
    assert last["headers"]["tr_id"] == "CTCA0903R"
    assert last["params"]["BASS_DT"] == "20260701"
    assert last["params"]["CTX_AREA_NK"] == "" and last["params"]["CTX_AREA_FK"] == ""
    assert holidays == [dt.date(2026, 8, 15), dt.date(2026, 1, 1)]


def test_get_holidays_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTCA0903R"] = []                      # pop → IndexError → []
    assert _client(t, fake_clock).get_holidays(dt.date(2026, 7, 1)) == []


def test_get_holidays_skips_unparseable_dates(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTCA0903R"] = [{"output": [
        {"bass_dt": "", "opnd_yn": "N"},                  # 빈 날짜 → 스킵
        {"bass_dt": "bad", "opnd_yn": "N"},               # 파싱불가 → 스킵
        {"bass_dt": "20260815", "opnd_yn": "N"}]}]
    assert _client(t, fake_clock).get_holidays(dt.date(2026, 7, 1)) == [dt.date(2026, 8, 15)]
