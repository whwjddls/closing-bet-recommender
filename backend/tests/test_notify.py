import datetime as dt
from types import SimpleNamespace

import pytest

from app.notify import (
    build_run_message,
    notify_run,
    public_board_url,
    send_telegram,
)


def _rec(rank, ticker, name, grade, price):
    return SimpleNamespace(rank=rank, ticker=ticker, name=name, grade=grade,
                           buy_price_provisional=price)


def _result(recs, reason="OK", funnel=None):
    regimes = {"KOSPI": SimpleNamespace(regime_mult=0.5),
               "KOSDAQ": SimpleNamespace(regime_mult=0.5)}
    return SimpleNamespace(recommendations=recs, regimes=regimes, reason=reason, funnel=funnel)


RUN_DATE = dt.date(2026, 7, 14)


# ── 텔레그램 발송 ────────────────────────────────────────────
def test_send_telegram_posts_to_bot_api():
    calls = []
    ok = send_telegram("hello", token="T", chat_id="42",
                       transport=lambda url, payload: calls.append((url, payload)))
    assert ok is True
    url, payload = calls[0]
    assert url == "https://api.telegram.org/botT/sendMessage"
    assert payload["chat_id"] == "42" and payload["text"] == "hello"


def test_send_telegram_returns_false_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    called = []
    assert send_telegram("hi", transport=lambda u, p: called.append(u)) is False
    assert called == []                      # 크리덴셜 없으면 네트워크 호출 자체를 안 한다


def test_send_telegram_swallows_transport_error():
    def boom(url, payload):
        raise ConnectionError("telegram down")

    # 알림 실패가 런을 깨뜨리면 안 된다(영속화는 이미 끝난 뒤 호출됨)
    assert send_telegram("hi", token="T", chat_id="1", transport=boom) is False


# ── 보드 링크 해소(env → state/public_url.txt) ────────────────
def test_public_board_url_prefers_env(monkeypatch):
    monkeypatch.setenv("CBR_PUBLIC_URL", "https://fixed.example.com/")
    assert public_board_url() == "https://fixed.example.com"


def test_public_board_url_reads_tunnel_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CBR_PUBLIC_URL", raising=False)
    monkeypatch.setenv("CBR_STATE_DIR", str(tmp_path))
    (tmp_path / "public_url.txt").write_text("https://abc.trycloudflare.com\n", encoding="utf-8")
    assert public_board_url() == "https://abc.trycloudflare.com"


def test_public_board_url_none_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("CBR_PUBLIC_URL", raising=False)
    monkeypatch.setenv("CBR_STATE_DIR", str(tmp_path))       # 파일 없음
    assert public_board_url() is None


# ── 메시지 본문 ──────────────────────────────────────────────
def test_build_run_message_lists_picks_and_link():
    recs = [_rec(1, "010950", "S-Oil", "S", 139500.0),
            _rec(2, "105560", "KB금융", "S", 186200.0)]
    text = build_run_message(_result(recs), run_date=RUN_DATE, url="https://x.example.com")
    assert "추천 2종목" in text
    assert "1. S-Oil(010950) S · 139,500원" in text
    assert "▶ 보드 열기: https://x.example.com" in text
    assert "15:20 잠정치" in text                     # 확정 종가 아님을 명시


def test_build_run_message_truncates_beyond_top_n():
    recs = [_rec(i, f"00{i}", f"종목{i}", "C", 1000.0 * i) for i in range(1, 13)]
    text = build_run_message(_result(recs), run_date=RUN_DATE)
    assert "종목5" in text and "종목6" not in text     # 상위 5개만
    assert "외 7종목" in text


def test_build_run_message_empty_board_carries_funnel_diagnosis():
    # 빈 보드에도 알림을 보내되 '왜' 비었는지 담는다 — 전략 탓/버그 탓 구분용.
    funnel = {"candidates": 200, "static_ok": 187, "quotes": 187, "dynamic_ok": 180,
              "shin_zero": 165, "veto_blocked": 3, "regime_zero": 0,
              "final_hygiene_dropped": 12}
    text = build_run_message(_result([], reason="RISK_OFF", funnel=funnel), run_date=RUN_DATE)
    assert "오늘 추천 없음" in text and "RISK_OFF" in text
    assert "후보 200" in text and "돌파미달 165" in text
    assert "공시veto 3" in text and "최종위생 12" in text


def test_build_run_message_omits_link_when_url_missing():
    text = build_run_message(_result([_rec(1, "005930", "삼성전자", "A", 70000.0)]),
                             run_date=RUN_DATE, url=None)
    assert "보드 열기" not in text


# ── notify_run: 텔레그램 실패 시 데스크톱 폴백 ────────────────
def test_notify_run_falls_back_to_desktop_when_telegram_unavailable():
    desktop = []
    notify_run(_result([_rec(1, "005930", "삼성전자", "A", 70000.0)]), run_date=RUN_DATE,
               notify=lambda t, m: desktop.append((t, m)),
               send=lambda text: False)              # 텔레그램 미설정
    assert desktop and "삼성전자" in desktop[0][1]


def test_notify_run_skips_desktop_when_telegram_succeeds():
    desktop = []
    notify_run(_result([_rec(1, "005930", "삼성전자", "A", 70000.0)]), run_date=RUN_DATE,
               notify=lambda t, m: desktop.append(t), send=lambda text: True)
    assert desktop == []                             # 중복 알림 금지
