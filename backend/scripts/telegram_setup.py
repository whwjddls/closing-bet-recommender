"""텔레그램 알림 설정 도우미 — chat_id 자동 확보 + 테스트 발송.

사용법:
  1) BotFather 에게 받은 토큰을 backend/.env 의 TELEGRAM_BOT_TOKEN= 에 붙여넣는다.
  2) python -m scripts.telegram_setup     (backend 디렉터리에서)
  3) 스크립트가 알려주는 t.me 링크로 봇 대화창을 열고 아무 메시지나 보낸다.
     → chat_id 를 잡아 .env 에 기록하고 테스트 메시지를 보낸다.

봇은 사람에게 먼저 말을 걸 수 없다 — 내가 봇에게 메시지를 보내기 전에는
getUpdates 가 항상 빈 배열({"ok":true,"result":[]})이다. 그래서 대기-폴링한다.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests

# Windows 콘솔 기본 코덱(cp949)은 em-dash 등을 못 찍어 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_ROOT / ".env"
API = "https://api.telegram.org/bot{token}/{method}"
POLL_SECONDS = 180
POLL_INTERVAL = 3


def _read_env_value(key: str) -> str:
    if not ENV_PATH.exists():
        return ""
    match = re.search(rf"^{key}=(.*)$", ENV_PATH.read_text(encoding="utf-8"), re.M)
    return match.group(1).strip() if match else ""


def _write_env_value(key: str, value: str) -> None:
    """.env 의 key= 줄을 갱신(없으면 추가). 다른 줄은 그대로 둔다."""
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    if re.search(rf"^{key}=.*$", text, re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{key}={value}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def _call(token: str, method: str, **params) -> dict:
    resp = requests.get(API.format(token=token, method=method), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _chat_from_updates(payload: dict) -> tuple[str, str] | None:
    for update in payload.get("result", []):
        message = update.get("message") or update.get("my_chat_member") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            name = chat.get("first_name") or chat.get("username") or "(이름없음)"
            return str(chat["id"]), name
    return None


def main() -> int:
    token = _read_env_value("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN 이 비어 있다.")
        print(f"  1) 텔레그램에서 @BotFather 에게 /newbot → 토큰 발급")
        print(f"  2) {ENV_PATH} 의 TELEGRAM_BOT_TOKEN= 뒤에 붙여넣고 다시 실행")
        return 1

    try:
        me = _call(token, "getMe")
    except Exception as exc:                            # noqa: BLE001
        print(f"토큰 확인 실패(네트워크/토큰 오류): {exc}")
        return 1
    if not me.get("ok"):
        print(f"토큰이 유효하지 않다: {me.get('description')}")
        return 1

    username = me["result"].get("username", "")
    print(f"봇 확인: @{username}")

    existing = _read_env_value("TELEGRAM_CHAT_ID")
    chat = None
    if existing:
        print(f"기존 TELEGRAM_CHAT_ID={existing} 사용")
        chat = (existing, "(기존 설정)")
    else:
        print(f"\n▶ https://t.me/{username} 를 열고 [시작] 을 누른 뒤 아무 메시지나 보내세요.")
        print(f"  (봇은 먼저 말을 걸 수 없어서, 내가 보내야 chat_id 가 잡힙니다)")
        print(f"  최대 {POLL_SECONDS}초 대기합니다...\n")
        deadline = time.time() + POLL_SECONDS
        while time.time() < deadline:
            found = _chat_from_updates(_call(token, "getUpdates"))
            if found:
                chat = found
                break
            time.sleep(POLL_INTERVAL)

    if chat is None:
        print("메시지를 못 받았다 — 봇 대화창에서 메시지를 보낸 뒤 다시 실행하세요.")
        return 1

    chat_id, who = chat
    _write_env_value("TELEGRAM_BOT_TOKEN", token)
    _write_env_value("TELEGRAM_CHAT_ID", chat_id)
    print(f"chat_id={chat_id} ({who}) → .env 에 기록했습니다.")

    sent = _call(token, "sendMessage", chat_id=chat_id,
                 text="[종가베팅] 알림 연결 완료 ✅\n매일 15:20 스캔 결과가 여기로 옵니다.")
    if sent.get("ok"):
        print("테스트 메시지를 보냈습니다 — 폰을 확인하세요.")
        return 0
    print(f"테스트 발송 실패: {sent.get('description')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
