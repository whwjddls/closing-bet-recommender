"""가격 규칙 (행마다 결정론).

매수가(표시) = 15:20 잠정 스냅샷(현재가와 동일) → 익일 확정 종가로 대체(스냅샷 둘 다 보관).
청산(주 CTA·채점) = 익일 오전 VWAP(09:00–10:00) 매도.
목표/손절(참고·'보유 시'·15:20 잠정값 freeze):
  손절 = max(매수가 − 1.0·ATR20, 매수가·0.97)
  목표 = 직전 전고점 > 매수가 ? min(매수가 + 1.2·ATR20, 직전 전고점) : 매수가 + 1.2·ATR20
"""
from __future__ import annotations

from dataclasses import dataclass

ATR_K = 1.2
STOP_ATR_K = 1.0
STOP_FLOOR_PCT = 0.97
EXIT_CTA = "익일 오전 VWAP(09:00–10:00) 매도"


def stop_price(buy_price: float, atr20: float) -> float:
    return max(buy_price - STOP_ATR_K * atr20, buy_price * STOP_FLOOR_PCT)


def target_price(buy_price: float, atr20: float, prev_high: float) -> float:
    if prev_high > buy_price:
        return min(buy_price + ATR_K * atr20, prev_high)
    return buy_price + ATR_K * atr20


@dataclass(frozen=True)
class FrozenPricing:
    buy_price_provisional: float
    target_price: float
    stop_price: float
    exit_cta: str


def freeze_prices(p_now_provisional: float, atr20: float, prev_high: float) -> FrozenPricing:
    buy = p_now_provisional
    return FrozenPricing(
        buy_price_provisional=buy,
        target_price=target_price(buy, atr20, prev_high),
        stop_price=stop_price(buy, atr20),
        exit_cta=EXIT_CTA,
    )
