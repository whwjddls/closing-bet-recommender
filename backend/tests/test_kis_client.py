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


# 분봉 TR(FHKST03010200) 실측 계약(2026-07-17 실호출로 확인):
# - FID_PW_DATA_INCU_YN 누락 시 rt_cd='2' 반려(ERROR INPUT FIELD NOT FOUND)
# - 호출당 최대 30봉 → 09:00–10:00 전체는 HOUR_1=093000/100000 2회 필요
# - 날짜 파라미터 없음(당일 전용) — 휴장일엔 직전 세션 봉이 stck_bsop_date 에 그대로 옴
def _minute_bar(bsop_date, hhmmss, price, vol):
    return {"stck_bsop_date": bsop_date, "stck_cntg_hour": hhmmss,
            "stck_prpr": price, "cntg_vol": vol}


def test_fetch_morning_vwaps_computes_both_windows_from_same_bars(fake_clock):
    # 판정 기준 09:00–09:20(종가베팅 청산 창) + 보조 09:00–10:00(비교 검증) —
    # 같은 분봉 2회 호출에서 두 값 모두 산출(추가 API 호출 없음).
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [
        {"rt_cd": "0", "output2": [
            _minute_bar("20260701", "090100", "100", "10"),
            _minute_bar("20260701", "091500", "104", "10"),
            _minute_bar("20260701", "092500", "120", "20"),    # 0920 밖·1000 안
            _minute_bar("20260701", "085900", "999", "100"),   # 개장 전 — 둘 다 밖
        ]},
        {"rt_cd": "0", "output2": [
            _minute_bar("20260701", "095900", "110", "40"),
            _minute_bar("20260701", "101500", "999", "100"),   # 10시 밖
        ]},
    ]
    v = _client(t, fake_clock).fetch_morning_vwaps("000660", dt.date(2026, 7, 1))
    # 0920: (100*10+104*10)/20 = 102.0 / 1000: (100*10+104*10+120*20+110*40)/80 = 110.5
    assert v.vwap_0900_0920 == pytest.approx(102.0)
    assert v.vwap_0900_1000 == pytest.approx(110.5)
    minute_calls = [c for c in t.calls if c["headers"].get("tr_id") == "FHKST03010200"]
    assert len(minute_calls) == 2                       # 30봉 한계 → 반쪽 창 2회 그대로
    hours = {c["params"]["FID_INPUT_HOUR_1"] for c in minute_calls}
    assert hours == {"093000", "100000"}
    assert all(c["params"]["FID_PW_DATA_INCU_YN"] == "Y" for c in minute_calls)


def test_fetch_morning_vwaps_0920_none_when_no_early_trades(fake_clock):
    # 9:20 이전 거래 결측(잠김 등) → 판정 창만 None, 보조 창은 산출.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [
        {"rt_cd": "0", "output2": [_minute_bar("20260701", "092500", "120", "20")]},
        {"rt_cd": "0", "output2": [_minute_bar("20260701", "095900", "110", "40")]},
    ]
    v = _client(t, fake_clock).fetch_morning_vwaps("000660", dt.date(2026, 7, 1))
    assert v.vwap_0900_0920 is None
    assert v.vwap_0900_1000 == pytest.approx((120 * 20 + 110 * 40) / 60)


def test_fetch_morning_vwaps_drops_stale_session_bars(fake_clock):
    # 실측(2026-07-17 제헌절): 휴장일 호출 → 전 봉이 stck_bsop_date=20260716.
    # 대상일 봉이 아니면 버려야 한다 — 직전 세션으로 채점하는 룩어헤드 오염 방지.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [
        {"rt_cd": "0", "output2": [_minute_bar("20260716", "091000", "692000", "500")]},
        {"rt_cd": "0", "output2": [_minute_bar("20260716", "100000", "692000", "500")]},
    ]
    v = _client(t, fake_clock).fetch_morning_vwaps("000810", dt.date(2026, 7, 17))
    assert v.vwap_0900_0920 is None
    assert v.vwap_0900_1000 is None


def test_fetch_morning_vwaps_raises_on_error_rt_cd(fake_clock):
    # 실측: 필수 필드 누락 시 rt_cd='2' — 조용한 None 은 NA 영구 잠금으로 이어졌다.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [
        {"rt_cd": "2", "msg1": "ERROR INPUT FIELD NOT FOUND [FID_PW_DATA_INCU_YN]",
         "output2": []},
    ]
    with pytest.raises(RuntimeError, match="FID_PW_DATA_INCU_YN"):
        _client(t, fake_clock).fetch_morning_vwaps("000660", dt.date(2026, 7, 1))


def test_fetch_morning_vwaps_none_when_empty(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST03010200"] = [{"rt_cd": "0", "output2": []},
                                       {"rt_cd": "0", "output2": []}]
    v = _client(t, fake_clock).fetch_morning_vwaps("000660", dt.date(2026, 7, 1))
    assert v.vwap_0900_0920 is None
    assert v.vwap_0900_1000 is None


def test_value_ranking_tr_id_and_parsing(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01710000"] = [{"output": [
        {"mksc_shrn_iscd": "000660", "hts_kor_isnm": "SK하이닉스",
         "acml_tr_pbmn": "1000", "data_rank": "1"},
        {"mksc_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자",
         "acml_tr_pbmn": "900", "data_rank": "2"}]}]
    entries = _client(t, fake_clock).get_value_ranking(Market.KOSPI)
    assert t.calls[-1]["headers"]["tr_id"] == "FHPST01710000"
    assert entries[0].ticker == "000660"
    assert entries[0].value == 1000.0
    assert entries[0].rank == 1
    assert entries[0].name == "SK하이닉스"    # 종목명 — 코드만 표기되는 UX 결함 방지


def test_volume_surge_ranking_uses_increase_rate_blng_code(fake_clock):
    # 당일 거래증가율(≈RVOL) 랭킹 — 같은 volume-rank TR 을 FID_BLNG_CLS_CODE="1" 로 호출.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHPST01710000"] = [
        {"output": [{"mksc_shrn_iscd": "247540", "hts_kor_isnm": "에코프로비엠",
                     "acml_tr_pbmn": "500", "data_rank": "1"}]},
        {"output": []},                       # 두 번째 호출(get_value_ranking)용
    ]
    client = _client(t, fake_clock)           # 단일 인스턴스 — 토큰 1회 발급 후 재사용
    entries = client.get_volume_surge_ranking(Market.KOSDAQ)
    assert t.calls[-1]["headers"]["tr_id"] == "FHPST01710000"
    assert t.calls[-1]["params"]["FID_BLNG_CLS_CODE"] == "1"   # 거래증가율(RVOL) 정렬
    assert entries[0].ticker == "247540"
    # 거래대금순과 정렬기준만 다르다(같은 TR) — 거래대금순은 "3"
    client.get_value_ranking(Market.KOSDAQ)
    assert t.calls[-1]["params"]["FID_BLNG_CLS_CODE"] == "3"


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
    # 실측 KIS 응답: 보통주 stck_kind_cd=101, mrkt_warn_cls_code 는 None 로 오기도 한다.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": "SK하이닉스", "admn_item_yn": "N",
        "mrkt_warn_cls_code": None, "stck_kind_cd": "101"}}]
    info = _client(t, fake_clock).get_stock_basic_info("000660")
    assert t.calls[-1]["headers"]["tr_id"] == "CTPF1002R"
    assert t.calls[-1]["params"]["PDNO"] == "000660"
    assert info["name"] == "SK하이닉스"
    assert info["is_managed"] is False
    assert info["is_preferred"] is False        # 101=보통주 (우선주 오판 → 보드 전멸 회귀 방지)
    assert info["is_ineligible"] is False


@pytest.mark.parametrize("kind,name", [
    ("201", "삼성전자우"),        # 우선주(구형)
    ("202", "현대차2우B"),        # 우선주(신형)
])
def test_get_stock_basic_info_flags_preferred_by_kind_code(fake_clock, kind, name):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": name, "admn_item_yn": "N",
        "mrkt_warn_cls_code": "00", "stck_kind_cd": kind}}]
    info = _client(t, fake_clock).get_stock_basic_info("005935")
    assert info["is_preferred"] is True
    assert info["is_ineligible"] is True


@pytest.mark.parametrize("name", ["우리금융지주", "한국항공우주", "대우건설"])
def test_get_stock_basic_info_common_stock_with_woo_in_name_not_preferred(fake_clock, name):
    # 이름에 '우'가 들어가는 보통주(kind=101) 를 우선주로 오탐하면 안 된다.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": name, "admn_item_yn": "N",
        "mrkt_warn_cls_code": "00", "stck_kind_cd": "101"}}]
    info = _client(t, fake_clock).get_stock_basic_info("316140")
    assert info["is_preferred"] is False
    assert info["is_ineligible"] is False


def test_get_stock_basic_info_preferred_by_name_when_kind_missing(fake_clock):
    # 코드 결측 시 종목명 접미사('...우'/'...우B') 폴백으로 우선주 판정.
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": "S-Oil우", "admn_item_yn": "N"}}]
    info = _client(t, fake_clock).get_stock_basic_info("010955")
    assert info["is_preferred"] is True
    assert info["is_ineligible"] is True


def test_get_stock_basic_info_flags_managed_ineligible(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["CTPF1002R"] = [{"output": {
        "prdt_abrv_name": "관리주", "admn_item_yn": "Y", "stck_kind_cd": "101"}}]
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


# ── 종목 뉴스 제목(news-title) ─────────────────────────────
def test_get_news_titles_tr_id_and_parsing(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01011800"] = [{"output": [
        {"hts_pbnt_titl_cntt": "SK하이닉스 신고가", "data_dt": "20260701",
         "data_tm": "093015"},
        {"titl": "삼성전자 실적 발표", "data_dt": "20260701", "data_tm": "1430"}]}]
    items = _client(t, fake_clock).get_news_titles("000660")
    last = t.calls[-1]
    assert last["headers"]["tr_id"] == "FHKST01011800"
    assert last["params"]["FID_INPUT_ISCD"] == "000660"
    assert items[0] == {"datetime": "2026-07-01 09:30", "title": "SK하이닉스 신고가"}
    assert items[1] == {"datetime": "2026-07-01 14:30", "title": "삼성전자 실적 발표"}


def test_get_news_titles_caps_at_10(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01011800"] = [{"output": [
        {"titl": f"뉴스{i}", "data_dt": "20260701", "data_tm": "0900"}
        for i in range(15)]}]
    items = _client(t, fake_clock).get_news_titles("000660")
    assert len(items) == 10                               # 최대 10건


def test_get_news_titles_skips_titleless_and_tolerates_missing_datetime(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01011800"] = [{"output": [
        {"data_dt": "20260701"},                          # 제목 없음 → 스킵
        {"titl": "제목만 있음"}]}]                          # 날짜/시간 결측 → datetime ""
    items = _client(t, fake_clock).get_news_titles("000660")
    assert items == [{"datetime": "", "title": "제목만 있음"}]


def test_get_news_titles_graceful_on_error(fake_clock):
    t = RecordingTransport()
    t.token_responses = [_token()]
    t.tr_responses["FHKST01011800"] = []                  # pop → IndexError → []
    assert _client(t, fake_clock).get_news_titles("000660") == []


# ── 파일 공유 토큰 캐시: 인스턴스/프로세스 간 재사용(1분 1회 발급 제한 대응) ──
WALL_T0 = 1_784_524_651.0          # 벽시계 기준점(epoch) — 실측 토큰 iat 값


class _FakeWall:
    """주입형 벽시계 — 토큰 파일 만료(epoch) 판정용. 재부팅을 넘어 유효."""

    def __init__(self, t: float = WALL_T0): self.t = t
    def __call__(self) -> float: return self.t


def _cache_client(transport, clock, cache_path, wall=None):
    from app.data.kis_client import KisClient, KisConfig
    cfg = KisConfig(app_key="AK", app_secret="SK", base_url="https://x", account="1-1")
    return KisClient(transport, clock, cfg, token_cache=cache_path,
                     wall_now=wall or _FakeWall())


class _CountClock:
    def __init__(self): self.t = 1_000.0
    def now(self): return self.t
    def sleep(self, s): self.t += s


def test_token_cache_file_shared_across_instances(tmp_path):
    cache = tmp_path / "kis_token.json"
    issues = []
    def t1(method, url, **kw):
        if url.endswith("/oauth2/tokenP"):
            issues.append(1); return {"access_token": "TOK1", "expires_in": 86400}
        return {"output": {}}
    c1 = _cache_client(t1, _CountClock(), cache)
    c1._ensure_token()
    assert len(issues) == 1 and cache.exists()          # 발급 1회 + 파일 기록

    def t2(method, url, **kw):                          # 두 번째 인스턴스: 발급 시도하면 실패
        if url.endswith("/oauth2/tokenP"):
            raise AssertionError("should reuse cached token, not reissue")
        return {"output": {}}
    c2 = _cache_client(t2, _CountClock(), cache)
    assert c2._ensure_token() == "TOK1"                 # 파일 재사용, 재발급 없음


def test_token_issue_failure_falls_back_to_cached_file(tmp_path):
    import json
    cache = tmp_path / "kis_token.json"
    cache.write_text(json.dumps({"access_token": "CACHED",
                                 "expires_at_epoch": WALL_T0 + 3600,
                                 "key": "AK:https://x"}), encoding="utf-8")
    def boom(method, url, **kw):
        if url.endswith("/oauth2/tokenP"):
            import requests
            raise requests.exceptions.HTTPError("403 Forbidden")   # 발급 제한
        return {"output": {}}
    c = _cache_client(boom, _CountClock(), cache, wall=_FakeWall())
    assert c._ensure_token() == "CACHED"                # 403 이어도 캐시로 동작


def test_token_cache_expired_reissues(tmp_path):
    import json
    cache = tmp_path / "kis_token.json"
    cache.write_text(json.dumps({"access_token": "OLD",
                                 "expires_at_epoch": WALL_T0 - 10,
                                 "key": "AK:https://x"}), encoding="utf-8")
    def t(method, url, **kw):
        if url.endswith("/oauth2/tokenP"):
            return {"access_token": "NEW", "expires_in": 86400}
        return {"output": {}}
    c = _cache_client(t, _CountClock(), cache, wall=_FakeWall())
    assert c._ensure_token() == "NEW"                   # 만료 → 재발급 + 파일 갱신
    assert "NEW" in cache.read_text(encoding="utf-8")


# ── 재시작 후 만료 판정(2026-07-22 사고 회귀) ───────────────────────
# 영속 만료 시각을 monotonic 으로 적으면 재부팅 시 monotonic 이 0 으로 리셋돼
# "작은 현재값 < 큰 저장값"이 항상 참 → 만료 토큰을 영구 재사용(전 종목 시세 0).
# 파일은 벽시계 epoch 로만 적고, 프로세스 내부 판정만 monotonic 을 쓴다.
def test_token_cache_reissues_after_restart_when_wall_clock_expired(tmp_path):
    cache = tmp_path / "kis_token.json"
    issues = []

    def transport(method, url, **kw):
        if url.endswith("/oauth2/tokenP"):
            issues.append(1)
            return {"access_token": f"TOK{len(issues)}", "expires_in": 86400}
        return {"output": {}}

    # 프로세스 A: 가동 19일차(monotonic 큼)에 발급 → 파일 기록
    wall_a = _FakeWall(WALL_T0)
    clock_a = _CountClock(); clock_a.t = 1_656_958.0
    assert _cache_client(transport, clock_a, cache, wall=wall_a)._ensure_token() == "TOK1"

    # 프로세스 B: 재부팅 후(monotonic≈0) + 벽시계로는 25시간 경과(토큰 만료)
    wall_b = _FakeWall(WALL_T0 + 25 * 3600)
    clock_b = _CountClock(); clock_b.t = 12.0
    token = _cache_client(transport, clock_b, cache, wall=wall_b)._ensure_token()

    assert token == "TOK2"          # 만료 인지 → 재발급 (버그 시 "TOK1" 무한 재사용)
    assert len(issues) == 2


def test_token_cache_ignores_legacy_monotonic_field(tmp_path):
    # 디스크에 남은 구 포맷(monotonic expiry_ts)은 신뢰 불가 — 무시하고 재발급해야 한다.
    import json
    cache = tmp_path / "kis_token.json"
    cache.write_text(json.dumps({"access_token": "POISONED", "expiry_ts": 1_743_358.0,
                                 "key": "AK:https://x"}), encoding="utf-8")

    def transport(method, url, **kw):
        if url.endswith("/oauth2/tokenP"):
            return {"access_token": "FRESH", "expires_in": 86400}
        return {"output": {}}

    c = _cache_client(transport, _CountClock(), cache, wall=_FakeWall())
    assert c._ensure_token() == "FRESH"


def test_token_cache_file_stores_wall_clock_epoch(tmp_path):
    # 기록된 만료가 벽시계 epoch 여야 한다 — monotonic 을 적으면 재시작 후 오판.
    import json
    cache = tmp_path / "kis_token.json"

    def transport(method, url, **kw):
        if url.endswith("/oauth2/tokenP"):
            return {"access_token": "TOK", "expires_in": 86400}
        return {"output": {}}

    clock = _CountClock(); clock.t = 1_656_958.0        # monotonic 은 크게
    _cache_client(transport, clock, cache, wall=_FakeWall())._ensure_token()
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["expires_at_epoch"] == pytest.approx(WALL_T0 + 86400)
    assert "expiry_ts" not in saved                     # 구 필드 미기록


# ── Part B: 토큰 발급 스레드안전 — 동시 만료 감지에도 발급 transport 1회 ─────
def test_ensure_token_issues_once_under_concurrent_threads():
    # 여러 워커가 동시에 _ensure_token 을 호출(토큰 미보유 상태)해도, 발급 transport 는
    # RLock 이중검사로 정확히 1회만 실행돼야 한다(중복 발급 → KIS 1분1회 403 사고 방지).
    import threading
    import time

    from app.data.kis_client import KisClient, _RealClock

    issues: list[int] = []
    ilock = threading.Lock()

    def transport(method, url, *, headers=None, json=None, params=None):
        if url.endswith("/oauth2/tokenP"):
            with ilock:
                issues.append(1)
            time.sleep(0.02)            # 발급 경합 창을 넓혀 락 부재 시 중복 발급을 유도
            return {"access_token": "TOK", "expires_in": 86400}
        return {"output": {}}

    client = KisClient(transport, _RealClock(), _cfg())
    threads = [threading.Thread(target=client._ensure_token) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(issues) == 1              # 8스레드 동시 진입에도 발급은 1회
    assert client._ensure_token() == "TOK"
