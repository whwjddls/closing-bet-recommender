"""Rank-band overnight backtest for closing-bet universe expansion.

핵심 질문: rank 201~600 돌파+유동 종목이 rank 1~200 대비 실제로 수익이 나는가?
매매 프록시: D일 종가 근처 매수 → D+1일 시가(≈익일 09:00 VWAP 판정창 프록시) 청산.
overnight_ret = D+1_open / D_close - 1
"""
import sys, os, json, time
sys.path.insert(0, r"D:\work\git\closing-bet-recommender\backend")
os.chdir(r"D:\work\git\closing-bet-recommender\backend")
from app.config import load_env
load_env()
import datetime as dt
import pandas as pd
from pykrx import stock

# 결과/로그는 스크립트 옆(backend/scripts/)에 남긴다. 실행: KRX_ID/KRX_PW(.env) 필요.
_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_HERE, "bt_result.json")
LOG = os.path.join(_HERE, "bt_progress.txt")

def logp(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")
    print(msg, flush=True)

open(LOG, "w").close()

# 1) 실 거래일 목록 (KOSPI 지수 OHLCV로 확정)
end = dt.date(2026, 7, 16)
start = end - dt.timedelta(days=260)  # ~170 거래일 확보(60일 워밍업 + 평가창)
idx = stock.get_index_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), "1001")
days = [d.date() if hasattr(d, "date") else d for d in idx.index]
days = sorted(set(days))
logp(f"trading days: {len(days)} ({days[0]} ~ {days[-1]})")

# 2) 일자별 by_ticker 패널 수집 (시/종가/거래량/거래대금)
def fetch_day(d):
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        for attempt in range(3):
            try:
                df = stock.get_market_ohlcv_by_ticker(d.strftime("%Y%m%d"), mk)
                if df is not None and len(df) > 0 and "거래대금" in df.columns and df["거래대금"].sum() > 0:
                    df = df.copy()
                    df["market"] = mk
                    frames.append(df)
                    break
            except Exception as e:
                time.sleep(0.4)
        else:
            return None
    if not frames:
        return None
    out = pd.concat(frames)
    return out

records = {}  # day -> DataFrame(index=ticker, cols: 시가 종가 거래량 거래대금 등락률 market)
for i, d in enumerate(days):
    df = fetch_day(d)
    if df is None:
        logp(f"  [{i+1}/{len(days)}] {d} SKIP (empty)")
        continue
    keep = df[["시가", "종가", "거래량", "거래대금", "market"]].copy()
    records[d] = keep
    if (i + 1) % 10 == 0:
        logp(f"  [{i+1}/{len(days)}] {d} ok, tickers={len(keep)}")
    time.sleep(0.05)

good_days = sorted(records.keys())
logp(f"collected {len(good_days)} good days")

# 3) 패널 → close/open/value/volume wide 매트릭스
all_tickers = sorted(set().union(*[set(records[d].index) for d in good_days]))
close = pd.DataFrame(index=good_days, columns=all_tickers, dtype=float)
opn = pd.DataFrame(index=good_days, columns=all_tickers, dtype=float)
value = pd.DataFrame(index=good_days, columns=all_tickers, dtype=float)
for d in good_days:
    r = records[d]
    close.loc[d, r.index] = r["종가"].values
    opn.loc[d, r.index] = r["시가"].values
    value.loc[d, r.index] = r["거래대금"].values
market_of = {}
for d in good_days:
    for t, mk in records[d]["market"].items():
        market_of[t] = mk

logp(f"panel: {close.shape}")

# 4) 평가: 60일 워밍업 후부터, 다음날 존재하는 날까지
WARM = 60
FLOOR = 1_000_000_000     # 10억 위생 하한(20일 평균거래대금)
NEAR_LOOSE = 0.90         # s_shin>0 근사(60일 고가 10% 이내)
NEAR_BASE = 0.97          # base_flag(베이스 상단)
COST = 0.005              # 왕복 비용/슬리피지 프록시 0.5%

bands = [(1, 200), (201, 400), (401, 600), (601, 1000)]
def band_of(rank):
    for lo, hi in bands:
        if lo <= rank <= hi:
            return f"{lo}-{hi}"
    return ">1000"

rows = []  # per (day, ticker) candidate record
eval_days = good_days[WARM:-1]  # 마지막날은 D+1 없음
logp(f"eval days: {len(eval_days)} ({eval_days[0]} ~ {eval_days[-1]})")

for di, d in enumerate(good_days):
    if d not in eval_days:
        continue
    idx_d = good_days.index(d)
    d1 = good_days[idx_d + 1]
    hist = close.iloc[idx_d - WARM + 1: idx_d + 1]  # 최근 60일 종가(당일 포함)
    val20 = value.iloc[idx_d - 19: idx_d + 1].mean()  # 20일 평균거래대금
    day_val = value.loc[d]                            # 당일 거래대금(랭킹 기준)
    c_d = close.loc[d]
    o_d1 = opn.loc[d1]
    c_d1 = close.loc[d1]

    valid = day_val.dropna()
    valid = valid[valid > 0]
    ranked = valid.sort_values(ascending=False)
    rank_map = {t: i + 1 for i, t in enumerate(ranked.index)}

    hi60 = hist.max()
    for t in ranked.index:
        cd = c_d.get(t)
        h = hi60.get(t)
        if not (cd and h and h > 0):
            continue
        near = cd / h
        if near < NEAR_LOOSE:
            continue
        if not (val20.get(t, 0) >= FLOOR):
            continue
        od1 = o_d1.get(t)
        if not (od1 and od1 > 0):
            continue
        overnight = od1 / cd - 1.0
        rank = rank_map[t]
        rows.append({
            "day": str(d), "ticker": t, "market": market_of.get(t, "?"),
            "rank": rank, "band": band_of(rank),
            "near60": round(float(near), 4),
            "base": bool(near >= NEAR_BASE),
            "val20_eok": round(float(val20.get(t, 0)) / 1e8, 1),
            "overnight": round(float(overnight), 5),
        })

df = pd.DataFrame(rows)
logp(f"candidate-days: {len(df)}")

def stats(sub, label):
    n = len(sub)
    if n == 0:
        return {"label": label, "n": 0}
    ov = sub["overnight"]
    return {
        "label": label, "n": int(n),
        "win_gt0_pct": round(float((ov > 0).mean() * 100), 1),
        "win_gt_cost_pct": round(float((ov > COST).mean() * 100), 1),
        "mean_pct": round(float(ov.mean() * 100), 3),
        "median_pct": round(float(ov.median() * 100), 3),
        "mean_after_cost_pct": round(float((ov - COST).mean() * 100), 3),
        "p90_pct": round(float(ov.quantile(0.9) * 100), 2),
        "p10_pct": round(float(ov.quantile(0.1) * 100), 2),
        "tail_ge2pct": round(float((ov >= 0.02).mean() * 100), 1),
    }

result = {"meta": {
    "eval_days": len(eval_days), "range": [str(eval_days[0]), str(eval_days[-1])],
    "warm": WARM, "floor_eok": 10, "near_loose": NEAR_LOOSE, "cost_pct": COST * 100,
    "total_candidate_days": len(df)},
}

# 밴드별 (near60>=0.90 전체 돌파후보)
result["by_band_loose"] = [stats(df[df["band"] == f"{lo}-{hi}"], f"{lo}-{hi}") for lo, hi in bands]
# 밴드별 (base breakout near>=0.97 — 실제 발행에 가까운 강한 신호)
b = df[df["base"]]
result["by_band_base"] = [stats(b[b["band"] == f"{lo}-{hi}"], f"{lo}-{hi} base") for lo, hi in bands]

# 확대 시나리오: top200 vs top600 마진 (일평균 픽 수 + 수익성)
for cut in (200, 400, 600):
    sub = df[df["rank"] <= cut]
    subb = b[b["rank"] <= cut]
    result[f"cut_{cut}"] = {
        "loose": stats(sub, f"rank<= {cut} loose"),
        "base": stats(subb, f"rank<= {cut} base"),
        "picks_per_day_loose": round(len(sub) / len(eval_days), 1),
        "picks_per_day_base": round(len(subb) / len(eval_days), 1),
    }

# 마진 구간 201-600 만의 순수 기여
marg = df[(df["rank"] >= 201) & (df["rank"] <= 600)]
margb = b[(b["rank"] >= 201) & (b["rank"] <= 600)]
result["margin_201_600"] = {"loose": stats(marg, "201-600 loose"), "base": stats(margb, "201-600 base")}

# 시장별
for mk in ("KOSPI", "KOSDAQ"):
    result[f"market_{mk}"] = {
        "in200": stats(df[(df["market"] == mk) & (df["rank"] <= 200)], f"{mk} rank<=200"),
        "201_600": stats(df[(df["market"] == mk) & (df["rank"] >= 201) & (df["rank"] <= 600)], f"{mk} 201-600"),
    }

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
logp("DONE -> " + OUT)
