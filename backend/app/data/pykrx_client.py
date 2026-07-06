from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from app.data.broker_adapter import HealthCheckResult
from app.data.mapping import Market, pykrx_index_code, pykrx_market_name

COL_OPEN = "시가"
COL_HIGH = "고가"
COL_LOW = "저가"
COL_CLOSE = "종가"
COL_VOLUME = "거래량"
COL_VALUE = "거래대금"
COL_CHANGE_PCT = "등락률"
NET_VALUE_COL = "순매수거래대금"
# pykrx get_market_net_purchases_of_equities 의 investor 인자는 '투자자 유형'.
# 외인+기관 순매수액 = '외국인' + '기관합계' 를 종목별 합산(아키텍처 §3.2-D).
NET_INVESTORS = ("외국인", "기관합계")
LOOKBACK_DAYS = 400  # ≥252 거래일 확보용 달력 룩백


@dataclass
class HealthResult:
    """00 §2 정본 — 무인자 health_check() 반환형."""
    ok: bool
    latest_trading_day: dt.date | None
    rows: int
    detail: str


def compute_h_ref(df: Any, window: int) -> float:
    """H_ref = 제공된 (전일까지 확정) 프레임의 마지막 window 고가 최대. 룩어헤드 금지."""
    highs = df[COL_HIGH].tail(window)
    if len(highs) == 0:
        raise ValueError("empty high series")
    return float(highs.max())


def compute_atr20(df: Any, window: int = 20) -> float:
    sub = df.tail(window + 1)  # 직전 종가 필요
    high = sub[COL_HIGH].to_numpy(dtype=float)
    low = sub[COL_LOW].to_numpy(dtype=float)
    close = sub[COL_CLOSE].to_numpy(dtype=float)
    trs = []
    for i in range(1, len(sub)):
        tr = max(high[i] - low[i],
                 abs(high[i] - close[i - 1]),
                 abs(low[i] - close[i - 1]))
        trs.append(tr)
    if not trs:
        raise ValueError("insufficient rows for ATR")
    return sum(trs) / len(trs)


def compute_avg_value_20d(df: Any, window: int = 20) -> float:
    # 실 pykrx 시계열 OHLCV 는 '거래대금' 컬럼이 없다(종가·거래량만). 없으면 종가×거래량으로 파생.
    if COL_VALUE in getattr(df, "columns", []):
        vals = df[COL_VALUE].tail(window)
    else:
        tail = df.tail(window)
        vals = tail[COL_CLOSE].astype(float) * tail[COL_VOLUME].astype(float)
    if len(vals) == 0:
        raise ValueError("empty value series")
    return float(vals.mean())


class PykrxClient:
    """FINAL 소스. pykrx 모듈은 주입 → 네트워크 없는 단위테스트."""

    def __init__(self, pykrx_module: Any, min_rows: int = 120):
        self._px = pykrx_module
        self._min_rows = min_rows

    def get_universe(self, date: str, market: str = "ALL") -> list[str]:
        # 생존편향 방지: as-of date 그대로 전달(point-in-time)
        return list(self._px.get_market_ticker_list(date, market))

    def get_ohlcv(self, ticker: str, fromdate: str, todate: str) -> Any:
        # 룩어헤드 방지: todate(=D-1)를 그대로 전달, 당일(t) 바 미요청
        return self._px.get_market_ohlcv(fromdate, todate, ticker)

    def get_index_ohlcv(self, index_code: str, fromdate: str, todate: str) -> Any:
        return self._px.get_index_ohlcv(fromdate, todate, index_code)

    def get_net_purchases(self, fromdate: str, todate: str) -> dict[str, float]:
        # 시장별 1회 = 총 2회, 순매수거래대금(value) 컬럼 (per-ticker 금지)
        return _net_by_market(self._px, fromdate, todate)

    def health_check(self, df: Any, expected_last_date: str | None) -> HealthCheckResult:
        if df is None or len(df) == 0:
            return HealthCheckResult(False, None, 0, "no rows")
        last = str(df.index[-1])
        rows = len(df)
        if rows < self._min_rows:
            return HealthCheckResult(
                False, last, rows, f"insufficient rows {rows}<{self._min_rows}")
        if expected_last_date and last != expected_last_date:
            return HealthCheckResult(
                False, last, rows, f"stale last={last} expected={expected_last_date}")
        return HealthCheckResult(True, last, rows)


# ── 모듈 정본 인터페이스(00 §2) — 04 스케줄러/어댑터가 호출 ──────────────
def _load_pykrx() -> Any:
    from pykrx import stock
    return stock


def _yyyymmdd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _parse_day(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.datetime.strptime(str(value), "%Y%m%d").date()
    except ValueError:
        return None


def _net_by_market(px: Any, fromdate: str, todate: str) -> dict[str, float]:
    """외인+기관 순매수거래대금 — 시장×투자자유형(외국인/기관합계) 조회 후 종목별 합산."""
    result: dict[str, float] = {}
    for market in (Market.KOSPI, Market.KOSDAQ):
        for investor in NET_INVESTORS:
            df = px.get_market_net_purchases_of_equities(
                fromdate, todate, pykrx_market_name(market), investor)
            if df is None or NET_VALUE_COL not in getattr(df, "columns", []):
                continue
            for ticker, row in df.iterrows():
                result[str(ticker)] = result.get(str(ticker), 0.0) + float(row[NET_VALUE_COL])
    return result


@dataclass
class PrefetchBundle:
    """장전 FINAL 번들(00 §2)."""
    run_date: dt.date
    universe: list[str]
    h_ref_252: dict[str, float]
    h_ref_60: dict[str, float]
    atr20: dict[str, float]
    avg_value_20d: dict[str, float]
    net_purchases: dict[str, float]
    index_ma5: dict[str, float]
    market_of: dict[str, str] = field(default_factory=dict)   # 종목→시장(top200 선정 시 확보)


TOP_VALUE_UNIVERSE_N = 200          # D-1 거래대금 상위 유니버스 크기(KOSPI∪KOSDAQ)


def select_top_value_universe(px: Any, d1_s: str,
                              top_n: int = TOP_VALUE_UNIVERSE_N) -> tuple[list[str], dict[str, str]]:
    """D-1 거래대금 상위 top_n 유니버스(KOSPI∪KOSDAQ). get_market_ohlcv_by_ticker 2회.

    반환 (tickers, market_of). 조회 실패/컬럼 부재 시 방어적으로 건너뛴다."""
    pairs: list[tuple[str, float]] = []
    market_of: dict[str, str] = {}
    for market in (Market.KOSPI, Market.KOSDAQ):
        try:
            df = px.get_market_ohlcv_by_ticker(d1_s, pykrx_market_name(market))
        except Exception:                                   # noqa: BLE001  (외부 IO)
            continue
        if df is None or len(df) == 0 or COL_VALUE not in getattr(df, "columns", []):
            continue
        for ticker, row in df.iterrows():
            t = str(ticker)
            pairs.append((t, float(row[COL_VALUE])))
            market_of.setdefault(t, market.value)
    pairs.sort(key=lambda p: p[1], reverse=True)            # 거래대금 내림차순
    out: list[str] = []
    seen: set[str] = set()
    for ticker, _value in pairs:
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
        if len(out) >= top_n:
            break
    return out, {t: market_of[t] for t in out}


def prefetch_top_value(run_date: dt.date, pykrx_module: Any | None = None,
                       top_n: int = TOP_VALUE_UNIVERSE_N) -> PrefetchBundle:
    """장전 기본 prefetch — D-1 거래대금 상위 top_n 유니버스만 FINAL 번들로 산출.

    전 종목 스캔(수천 콜) 대신 top200 만 OHLCV 조회해 15:20 풀 폭주를 막는다(00 §2/T1)."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    d1 = run_date - dt.timedelta(days=1)
    universe, market_of = select_top_value_universe(px, _yyyymmdd(d1), top_n)
    return prefetch_final(run_date, px, universe=universe, market_of=market_of)


def prefetch_final(run_date: dt.date, pykrx_module: Any | None = None,
                   universe: list[str] | None = None,
                   market_of: dict[str, str] | None = None) -> PrefetchBundle:
    """H_ref(252/60)·ATR20·20일평균거래대금·D-1수급·지수5MA·정적위생 후보 번들.
       룩어헤드 금지 — 모든 조회 todate=D-1. pykrx 모듈 주입(미주입 시 실모듈).

       universe 주입 시 그 목록만 순회(top200 등), 미주입 시 전 종목(하위호환)."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    d1 = run_date - dt.timedelta(days=1)
    frm = run_date - dt.timedelta(days=LOOKBACK_DAYS)
    d1_s, frm_s = _yyyymmdd(d1), _yyyymmdd(frm)
    if universe is None:
        universe = [str(t) for t in px.get_market_ticker_list(d1_s, "ALL")]
    market_of = dict(market_of or {})
    h252: dict[str, float] = {}
    h60: dict[str, float] = {}
    atr: dict[str, float] = {}
    avgv: dict[str, float] = {}
    for ticker in universe:
        df = px.get_market_ohlcv(frm_s, d1_s, ticker)   # todate=D-1 (룩어헤드 금지)
        if df is None or len(df) == 0:
            continue
        try:
            _h252 = compute_h_ref(df, 252)
            _h60 = compute_h_ref(df, 60)
            _atr = compute_atr20(df)
            _avgv = compute_avg_value_20d(df)
        except ValueError:
            continue                                    # 이력 부족 종목 스킵(방어적)
        h252[ticker], h60[ticker] = _h252, _h60
        atr[ticker], avgv[ticker] = _atr, _avgv
    net = _net_by_market(px, d1_s, d1_s)                # D-1 수급
    index_ma5: dict[str, float] = {}
    for market in (Market.KOSPI, Market.KOSDAQ):
        idx = px.get_index_ohlcv(frm_s, d1_s, pykrx_index_code(market))
        if idx is not None and len(idx) > 0:
            index_ma5[market.value] = float(idx[COL_CLOSE].tail(5).mean())
    return PrefetchBundle(run_date, universe, h252, h60, atr, avgv, net, index_ma5,
                          market_of=market_of)


def fetch_confirmed_close(ticker: str, d: dt.date,
                          pykrx_module: Any | None = None) -> float:
    """익일 채점용 15:30 확정 종가(00 §2). 채점일 d는 과거 확정일 — 룩어헤드 아님."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    d_s = _yyyymmdd(d)
    df = px.get_market_ohlcv(d_s, d_s, ticker)
    if df is None or len(df) == 0:
        raise ValueError(f"no confirmed close for {ticker} on {d_s}")
    return float(df[COL_CLOSE].iloc[-1])


CHART_LOOKBACK_DAYS = 400        # ≥252 거래일 확보용 달력 룩백
CHART_CANDLE_COUNT = 60          # 상세 차트에 노출할 최근 캔들 수
WINDOW_52W = 252                 # 52주 신고가 윈도우(거래일)
PRIOR_HIGH_WINDOW = 60           # 직전고점(돌파 저항) 윈도우
BASE_BOX_WINDOW = 20             # 베이스박스(최근 정체 구간) 윈도우


def _index_date_str(value: Any) -> str:
    d = _parse_day(value)
    return d.strftime("%Y-%m-%d") if d else str(value)


def get_stock_chart(code: str, run_date: dt.date,
                    pykrx_module: Any | None = None) -> dict:
    """종목 상세 차트(00 §5): 최근 캔들·52주최고·직전고점·베이스박스.

    룩어헤드 금지 — todate=run_date(추천 산출일의 확정 종가일)까지만 조회한다.
    반환: ``{candles, high_52w, prior_high, base_box}``. 이력 없으면 빈 캔들·0 반환."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    todate = _yyyymmdd(run_date)
    frm = _yyyymmdd(run_date - dt.timedelta(days=CHART_LOOKBACK_DAYS))
    df = px.get_market_ohlcv(frm, todate, code)
    if df is None or len(df) == 0:
        return {"candles": [], "high_52w": 0.0, "prior_high": 0.0, "base_box": None}

    highs = df[COL_HIGH].astype(float)
    high_52w = float(highs.tail(WINDOW_52W).max())
    prior = highs.iloc[:-1].tail(PRIOR_HIGH_WINDOW)     # 당일 제외 직전고점(돌파 저항)
    prior_high = float(prior.max()) if len(prior) else float(highs.iloc[-1])

    box_df = df.tail(BASE_BOX_WINDOW)
    base_box = {
        "start": _index_date_str(box_df.index[0]),
        "end": _index_date_str(box_df.index[-1]),
        "low": float(box_df[COL_LOW].astype(float).min()),
        "high": float(box_df[COL_HIGH].astype(float).max()),
    }

    candles = [
        {
            "date": _index_date_str(idx),
            "open": float(row[COL_OPEN]),
            "high": float(row[COL_HIGH]),
            "low": float(row[COL_LOW]),
            "close": float(row[COL_CLOSE]),
            "volume": int(float(row[COL_VOLUME])),
        }
        for idx, row in df.tail(CHART_CANDLE_COUNT).iterrows()
    ]
    return {"candles": candles, "high_52w": high_52w,
            "prior_high": prior_high, "base_box": base_box}


OVERNIGHT_GAP_MIN_SAMPLES = 20          # 표본 <20이면 통계 무의미 → None
OVERNIGHT_GAP_WORST_PCTILE = 5          # worst5pct = 갭 분포 5퍼센타일(하방 꼬리)


def overnight_gap_stats(ticker: str, asof: dt.date, lookback_days: int = 252,
                        pykrx_module: Any | None = None) -> dict | None:
    """오버나잇 갭 통계(종가베팅 핵심 리스크). gap[t]=open[t+1]/close[t]-1 를 최근
    ``lookback_days`` 거래일 윈도우로 산출. 반환 ``{mean, std(모σ), worst5pct, n}``.

    룩어헤드 금지 — todate=asof 까지만 조회. 표본 <20이면 None(콜드스타트)."""
    import numpy as np

    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    todate = _yyyymmdd(asof)
    # lookback_days 거래일 갭 확보용 넉넉한 달력 룩백(주말·공휴일 감안 ×2)
    frm = _yyyymmdd(asof - dt.timedelta(days=lookback_days * 2))
    df = px.get_market_ohlcv(frm, todate, ticker)
    if df is None or len(df) < 2:
        return None
    opens = df[COL_OPEN].astype(float).to_numpy()
    closes = df[COL_CLOSE].astype(float).to_numpy()
    gaps = opens[1:] / closes[:-1] - 1.0                # gap[t]=open[t+1]/close[t]-1
    gaps = gaps[-lookback_days:]                         # 최근 lookback_days 갭만
    n = int(len(gaps))
    if n < OVERNIGHT_GAP_MIN_SAMPLES:
        return None
    return {
        "mean": float(gaps.mean()),
        "std": float(gaps.std()),                       # ddof=0 → 모표준편차
        "worst5pct": float(np.percentile(gaps, OVERNIGHT_GAP_WORST_PCTILE)),
        "n": n,
    }


def kospi_index_curve(start: dt.date, end: dt.date,
                      pykrx_module: Any | None = None) -> list[dict]:
    """KOSPI 지수 누적수익 곡선(성과추적 벤치마크). ``[start, end]`` 구간 종가를
    첫 종가 대비 누적수익(close/close[0]-1)으로 환산해 ``[{date, cum}]`` 반환.
    조회 실패/행 없음/기준가 0 → 빈 리스트(벤치마크 미가용 graceful)."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    frm_s, to_s = _yyyymmdd(start), _yyyymmdd(end)
    try:
        df = px.get_index_ohlcv(frm_s, to_s, pykrx_index_code(Market.KOSPI))
    except Exception:                                   # noqa: BLE001  (외부 IO)
        return []
    if df is None or len(df) == 0:
        return []
    closes = df[COL_CLOSE].astype(float).to_numpy()
    base = closes[0]
    if base == 0:
        return []
    return [
        {"date": _index_date_str(idx), "cum": float(close / base - 1.0)}
        for idx, close in zip(df.index, closes)
    ]


SUPPLY_5D_WINDOW = 5                     # 종목별 수급 노출 최근 거래일 수
SUPPLY_5D_LOOKBACK_DAYS = 15            # 5거래일 확보용 달력 룩백(주말·공휴일 감안)
SUPPLY_FOREIGN_COL = "외국인합계"     # pykrx get_market_trading_value_by_date 실제 컬럼명
SUPPLY_INSTITUTION_COL = "기관합계"


def supply_5d(ticker: str, asof: dt.date,
              pykrx_module: Any | None = None) -> dict | None:
    """종목별 최근 5거래일 외인·기관 순매수 거래대금(억). 룩어헤드 금지 —
    todate=asof 까지만 조회. 반환 ``{dates, foreign, institution}``(억 단위 float).
    조회 실패/행 없음 → None(미가용)."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    to_s = _yyyymmdd(asof)
    frm_s = _yyyymmdd(asof - dt.timedelta(days=SUPPLY_5D_LOOKBACK_DAYS))
    try:
        df = px.get_market_trading_value_by_date(frm_s, to_s, ticker)
    except Exception:                                   # noqa: BLE001  (외부 IO)
        return None
    if df is None or len(df) == 0:
        return None
    if SUPPLY_FOREIGN_COL not in df.columns or SUPPLY_INSTITUTION_COL not in df.columns:
        return None                                     # 컬럼 스키마 변동 시 500 대신 미가용
    tail = df.tail(SUPPLY_5D_WINDOW)
    foreign = tail[SUPPLY_FOREIGN_COL].astype(float).to_numpy() / EOK
    institution = tail[SUPPLY_INSTITUTION_COL].astype(float).to_numpy() / EOK
    return {
        "dates": [_index_date_str(idx) for idx in tail.index],
        "foreign": [float(v) for v in foreign],
        "institution": [float(v) for v in institution],
    }


def health_check(pykrx_module: Any | None = None, *,
                 today: dt.date | None = None, min_rows: int = 120) -> HealthResult:
    """무인자 장전 헬스체크(00 §2). 지수 OHLCV(todate=D-1) + D-1 외인/기관 수급·거래대금
       조회 성공을 함께 검증. 수급 결손 시 ok=False(런 차단). pykrx 모듈 주입."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    today = today or dt.date.today()
    d1 = today - dt.timedelta(days=1)
    frm = today - dt.timedelta(days=LOOKBACK_DAYS)
    d1_s, frm_s = _yyyymmdd(d1), _yyyymmdd(frm)
    try:
        idx = px.get_index_ohlcv(frm_s, d1_s, pykrx_index_code(Market.KOSPI))
    except Exception as exc:                            # noqa: BLE001  (외부 IO)
        return HealthResult(False, None, 0, f"지수 조회 실패: {exc}")
    if idx is None or len(idx) == 0:
        return HealthResult(False, None, 0, "지수 행 없음")
    latest = _parse_day(idx.index[-1])
    rows = len(idx)
    if rows < min_rows:
        return HealthResult(False, latest, rows,
                            f"insufficient rows {rows}<{min_rows}")
    # 수급은 달력 D-1(주말/휴일일 수 있음)이 아니라 지수 조회가 해소한 '실제 마지막
    # 거래일'로 조회한다 — 월요일·연휴 다음날 무거래일 조회로 인한 오탐 BLOCKED 방지.
    supply_day = _yyyymmdd(latest) if latest is not None else d1_s
    try:
        supply = _net_by_market(px, supply_day, supply_day)  # 실 마지막 거래일 외인/기관 수급
    except Exception as exc:                            # noqa: BLE001  (외부 IO)
        return HealthResult(False, latest, rows, f"D-1 수급 조회 실패: {exc}")
    if not supply:
        return HealthResult(False, latest, rows, "D-1 외인/기관 수급 결손")
    return HealthResult(True, latest, rows, "ok")


# ── /market 위젯: 시장 폭(breadth) + 업종 등락(sectors) ──────────────────
LIMIT_UP_PCT = 29.0             # 상한가 근접(+30% 근처) 임계
SECTOR_LOOKBACK_DAYS = 10       # 업종지수 종가-종가 등락 산출용 짧은 룩백
# 주요 KOSPI 업종지수(코드→명). pykrx get_index_ohlcv 로 종가-종가 등락 산출.
MARKET_SECTOR_INDICES: dict[str, str] = {
    "1005": "음식료품", "1008": "화학", "1009": "의약품", "1011": "철강금속",
    "1012": "기계", "1013": "전기전자", "1015": "운수장비", "1016": "유통업",
    "1018": "건설업", "1020": "통신업", "1021": "금융업", "1026": "서비스업",
}
_EMPTY_BREADTH: dict[str, int] = {
    "advancers": 0, "decliners": 0, "unchanged": 0, "new_highs": 0, "limit_ups": 0,
}


def latest_trading_day(pykrx_module: Any | None = None) -> dt.date:
    """pykrx 기준 최근 거래일. get_nearest_business_day_in_a_week() → date."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    day = _parse_day(px.get_nearest_business_day_in_a_week())
    return day or dt.date.today()


def market_breadth(asof: dt.date, pykrx_module: Any | None = None) -> dict:
    """시장 폭: 당일 스냅샷 등락률 부호로 상승/하락/보합 집계, +30% 근접 상한가 수,
    당일 고가에 종가 도달(신고가 근접) 수. 스냅샷 없으면 0 집계(200 유지)."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    df = px.get_market_ohlcv_by_ticker(_yyyymmdd(asof), "ALL")
    if df is None or len(df) == 0:
        return dict(_EMPTY_BREADTH)
    chg = df[COL_CHANGE_PCT].astype(float)
    close = df[COL_CLOSE].astype(float)
    high = df[COL_HIGH].astype(float)
    return {
        "advancers": int((chg > 0).sum()),
        "decliners": int((chg < 0).sum()),
        "unchanged": int((chg == 0).sum()),
        # 전 종목 252거래일 조회는 요청당 수천 콜이라 비현실적 → 당일 고가 도달을 신고가 근사로 집계
        "new_highs": int((close >= high).sum()),
        "limit_ups": int((chg >= LIMIT_UP_PCT).sum()),
    }


def sector_changes(asof: dt.date, pykrx_module: Any | None = None) -> list[dict]:
    """업종별 등락: 주요 업종지수 종가-종가 등락률(%)을 내림차순 정렬해 반환.
    지수 조회 실패/행 부족 종목은 건너뛴다(방어적). 결과 없으면 빈 리스트."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    to_s = _yyyymmdd(asof)
    frm_s = _yyyymmdd(asof - dt.timedelta(days=SECTOR_LOOKBACK_DAYS))
    out: list[dict] = []
    for code, name in MARKET_SECTOR_INDICES.items():
        try:
            df = px.get_index_ohlcv(frm_s, to_s, code)
        except Exception:                                   # noqa: BLE001  (외부 IO)
            continue
        if df is None or len(df) < 2:
            continue
        closes = df[COL_CLOSE].astype(float).to_numpy()
        change_pct = (closes[-1] / closes[-2] - 1.0) * 100.0
        out.append({"name": name, "change_pct": float(change_pct)})
    out.sort(key=lambda s: s["change_pct"], reverse=True)
    return out


INVESTOR_NET_COL = "순매수"             # pykrx 투자자별 거래대금 순매수 컬럼(원 단위)
EOK = 1e8                               # 억원 환산(1억 = 1e8원)
# 시장 전체 투자자 구분(pykrx 인덱스 라벨) → 응답 필드
INVESTOR_LABELS: dict[str, str] = {
    "foreign_net": "외국인",
    "institution_net": "기관합계",
    "individual_net": "개인",
}
_EMPTY_INVESTORS: dict[str, float] = {
    "foreign_net": 0.0, "institution_net": 0.0, "individual_net": 0.0,
}


def _investor_net(df: Any, label: str) -> float:
    """투자자 라벨의 순매수거래대금(원). 라벨 부재 시 0(방어적)."""
    if df is None or label not in df.index:
        return 0.0
    return float(df.loc[label, INVESTOR_NET_COL])


def market_investors(asof: dt.date, pykrx_module: Any | None = None) -> dict:
    """시장 전체 D-1(=asof, 최근 거래일) 외인/기관/개인 순매수 거래대금(억 단위 float).
    시장별 1회(총 2회) 조회 후 합산. 조회 실패/행 부족 시 0(200 유지, 방어적)."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    to_s = _yyyymmdd(asof)
    totals = dict(_EMPTY_INVESTORS)
    for market in (Market.KOSPI, Market.KOSDAQ):
        try:
            df = px.get_market_trading_value_by_investor(
                to_s, to_s, pykrx_market_name(market))
        except Exception:                                   # noqa: BLE001  (외부 IO)
            continue
        for field_name, label in INVESTOR_LABELS.items():
            totals[field_name] += _investor_net(df, label)
    return {k: v / EOK for k, v in totals.items()}          # 원 → 억


def market_overview(pykrx_module: Any | None = None) -> dict:
    """/market 데이터: 최근 거래일 기준 breadth + sectors + investors. pykrx 모듈 주입."""
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    asof = latest_trading_day(px)
    return {
        "asof": asof,
        "breadth": market_breadth(asof, px),
        "sectors": sector_changes(asof, px),
        "investors": market_investors(asof, px),
    }


# ── 참고 조회·신고가 위젯 지원 — KRX 상장 주식 판별/종목명 ──────────────────
# KIS 랭킹(near-new-highlow)은 ETF·ETN·채권펀드를 섞어 반환하는데, 이들은
# 전략 대상이 아니고 pykrx 주식 API(차트·수급)가 지원하지 않아 클릭 시
# 빈 화면이 된다. KRX 상장주식 목록과 교차검증해 걸러낸다.
_LISTED_CACHE: dict[str, frozenset[str]] = {}   # day_s → 상장주식 집합(프로세스 캐시)
_NAME_CACHE: dict[str, str] = {}                # ticker → 종목명


def listed_stock_set(day_s: str, pykrx_module: Any | None = None) -> frozenset[str]:
    """해당 일자 KRX 상장 주식(KOSPI∪KOSDAQ∪KONEX) 티커 집합. ETF·ETN·ELW 미포함.

    빈 결과는 캐시하지 않는다 — 휴장/일시 장애 시 다음 호출이 재시도한다."""
    cached = _LISTED_CACHE.get(day_s)
    if cached is not None:
        return cached
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    listed = frozenset(str(t) for t in px.get_market_ticker_list(day_s, "ALL"))
    if listed:
        _LISTED_CACHE[day_s] = listed
    return listed


def filter_listed_stocks(rows: list[dict], pykrx_module: Any | None = None,
                         today: dt.date | None = None) -> list[dict]:
    """KIS 랭킹 행에서 비주식(ETF·ETN·채권펀드 등)을 ticker 교차검증으로 제거.

    KRX 조회 실패·빈 목록이면 원본 그대로(fail-open) — 필터 장애로 위젯이
    통째로 비는 것보다 잡음 섞인 목록이 낫다."""
    day_s = _yyyymmdd(today or dt.date.today())
    try:
        listed = listed_stock_set(day_s, pykrx_module)
    except Exception:                                   # noqa: BLE001  (외부 IO)
        return rows
    if not listed:
        return rows
    return [r for r in rows if str(r.get("ticker", "")) in listed]


def stock_name(ticker: str, pykrx_module: Any | None = None) -> str | None:
    """KRX 종목명. 미상장(ETF 등)·조회 실패 시 None.

    실측(2026-07-03): pykrx는 미상장 티커에 문자열이 아닌 빈 DataFrame을 반환."""
    cached = _NAME_CACHE.get(ticker)
    if cached is not None:
        return cached
    px = pykrx_module if pykrx_module is not None else _load_pykrx()
    try:
        name = px.get_market_ticker_name(ticker)
    except Exception:                                   # noqa: BLE001  (외부 IO)
        return None
    if isinstance(name, str) and name:
        _NAME_CACHE[ticker] = name
        return name
    return None
