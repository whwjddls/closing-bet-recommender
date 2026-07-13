"""알림 — 텔레그램(폰) + 데스크톱 폴백.

15:20 런 결과를 폰으로 보낸다. 크리덴셜/네트워크 실패는 절대 런을 깨뜨리지 않는다
(알림은 best-effort — 이미 DB·스냅샷 영속화가 끝난 뒤 호출된다).

보드 링크는 ① ``CBR_PUBLIC_URL`` 환경변수 → ② ``state/public_url.txt``
(start.ps1 이 cloudflared 로그에서 감지해 기록) 순으로 해소한다. 둘 다 없으면 링크 생략.

**빈 보드일 때 퍼널 요약을 함께 보낸다** — "오늘 추천 없음"만 오면 전략 탓인지 버그
탓인지 알 수 없다. 단계별 생존 수가 있으면 폰에서 바로 판별된다.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
PUBLIC_URL_FILE = "public_url.txt"      # state/ 아래 — start.ps1 터널 감지 결과
TOP_N_NOTIFY = 5
HTTP_TIMEOUT_SEC = 10


def _default_transport(url: str, payload: dict) -> None:
    import requests

    resp = requests.post(url, json=payload, timeout=HTTP_TIMEOUT_SEC)
    resp.raise_for_status()


def public_board_url() -> str | None:
    """폰에서 열 보드 주소. env → state/public_url.txt 순. 없으면 None(링크 생략)."""
    from app.config import get_settings

    env_url = os.environ.get("CBR_PUBLIC_URL")
    if env_url:
        return env_url.strip().rstrip("/")
    path = get_settings().state_dir / PUBLIC_URL_FILE
    try:
        url = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return url.rstrip("/") or None


def send_telegram(text: str, *, token: str | None = None, chat_id: str | None = None,
                  transport: Callable[[str, dict], None] | None = None) -> bool:
    """텔레그램 발송. 크리덴셜 미설정/전송 실패는 False 반환(예외 전파 금지)."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.info("텔레그램 미설정(TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) — 발송 생략")
        return False
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        (transport or _default_transport)(TELEGRAM_API.format(token=token), payload)
    except Exception as exc:                    # noqa: BLE001  (알림은 best-effort)
        logger.warning("텔레그램 발송 실패: %s", exc)
        return False
    return True


def _funnel_line(funnel: dict | None) -> str:
    """빈 보드 진단용 한 줄 — 어느 단계에서 전멸했는지 폰에서 바로 읽는다."""
    if not funnel:
        return ""
    return (f"진단: 후보 {funnel.get('candidates', 0)} → 위생통과 {funnel.get('static_ok', 0)}"
            f" → 시세 {funnel.get('quotes', 0)} → 과열제외후 {funnel.get('dynamic_ok', 0)}"
            f"\n  탈락: 돌파미달 {funnel.get('shin_zero', 0)}"
            f" · 공시veto {funnel.get('veto_blocked', 0)}"
            f" · 리스크오프 {funnel.get('regime_zero', 0)}"
            f" · 최종위생 {funnel.get('final_hygiene_dropped', 0)}")


def build_run_message(result, *, run_date, session_type: str = "정규",
                      url: str | None = None) -> str:
    """15:20 런 결과 → 텔레그램 본문. 빈 보드면 퍼널 진단을 붙인다."""
    recs = sorted(result.recommendations, key=lambda r: r.rank)
    regimes = " / ".join(f"{m} {rg.regime_mult}" for m, rg in sorted(result.regimes.items()))
    head = f"[종가베팅 {run_date}{'' if session_type == '정규' else ' ·' + session_type}]"

    if not recs:
        body = (f"오늘 추천 없음 (사유: {result.reason})\n레짐: {regimes}\n\n"
                + _funnel_line(getattr(result, "funnel", None)))
    else:
        lines = [f"{r.rank}. {r.name}({r.ticker}) {r.grade} · "
                 f"{r.buy_price_provisional:,.0f}원" for r in recs[:TOP_N_NOTIFY]]
        more = f"\n… 외 {len(recs) - TOP_N_NOTIFY}종목" if len(recs) > TOP_N_NOTIFY else ""
        body = (f"추천 {len(recs)}종목 (레짐: {regimes})\n\n" + "\n".join(lines) + more
                + "\n\n※ 가격은 15:20 잠정치 — 종가로 확정됩니다")

    tail = f"\n\n▶ 보드 열기: {url}" if url else ""
    return f"{head}\n{body}{tail}"


def notify_run(result, *, run_date, session_type: str = "정규", notify=None,
               send=send_telegram) -> None:
    """런 결과 알림 — 텔레그램 우선, 실패 시 데스크톱 폴백. 예외를 전파하지 않는다."""
    text = build_run_message(result, run_date=run_date, session_type=session_type,
                             url=public_board_url())
    if send(text):
        return
    if notify is not None:                      # 텔레그램 미설정/실패 → 데스크톱 알림
        notify("종가베팅 추천 발행", text)
