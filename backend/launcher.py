"""종가베팅 데스크톱 런처 — EXE 진입점.

한 프로세스에서 셋을 관리한다:
  1) 웹서버(uvicorn) — 정적 프론트 + /api  → http://localhost:8010
  2) 내장 스케줄러    — 08:30 프리페치 / 15:18 스캔+텔레그램 / 10:05 채점
  3) cloudflared 터널 — 임시 주소를 감지해 state/public_url.txt 에 기록(알림 링크용)

트레이 아이콘에 상주한다. 창을 닫아도 계속 돌고, [종료] 를 눌러야 내려간다.
스케줄러는 프로세스가 떠 있어야 돌므로 부팅 시 자동 실행을 권장한다
(scripts/install_autostart.ps1).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_FILE = "launcher.log"


def _ensure_std_streams() -> None:
    """--noconsole EXE 는 sys.stdout/stderr 가 None 이다 — devnull 로 대체한다.

    uvicorn 기본 로깅이 ``stdout.isatty()`` 를 불러 기동이 죽고(실측 FATAL),
    pykrx 도 KRX 로그인 시 print() 를 해서 스케줄 잡 도중 같은 이유로 죽는다.
    파일 로깅(_setup_logging)이 진짜 출력 경로이므로 표준 스트림은 버려도 된다."""
    import io

    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, io.TextIOWrapper(
                open(os.devnull, "wb"), encoding="utf-8", errors="replace"))

HOST = "127.0.0.1"
PORT = 8010
LOCAL_URL = f"http://localhost:{PORT}"
TUNNEL_PATTERN = re.compile(rb"https://[a-z0-9-]+\.trycloudflare\.com")
TUNNEL_WAIT_SEC = 60
CLOUDFLARED_ENV = "CBR_CLOUDFLARED"
PUBLIC_URL_FILE = "public_url.txt"


def _find_cloudflared() -> Path | None:
    """cloudflared 실행파일 — env → EXE 옆 → PATH → 알려진 tools 경로."""
    override = os.environ.get(CLOUDFLARED_ENV)
    if override and Path(override).exists():
        return Path(override)

    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    beside = exe_dir / "cloudflared.exe"
    if beside.exists():
        return beside

    found = shutil.which("cloudflared")
    if found:
        return Path(found)

    fallback = Path.home() / "tools" / "cloudflared.exe"
    return fallback if fallback.exists() else None


class Tunnel:
    """cloudflared 임시 터널 — 주소를 감지해 파일에 기록(BOM 없이).

    임시 터널은 켤 때마다 주소가 바뀐다. 15:20 텔레그램 알림이 이 파일을 읽어
    '보드 열기' 링크로 붙이므로, 기동 때마다 최신 주소로 덮어쓴다."""

    def __init__(self, state_dir: Path):
        self._state_dir = state_dir
        self._proc: subprocess.Popen | None = None
        self._log_path: Path | None = None
        self.url: str | None = None

    def _cleanup_old_logs(self) -> None:
        """이전 실행이 남긴 로그 정리(잡혀 있으면 조용히 건너뛴다)."""
        for old in self._state_dir.glob("cloudflared-*.log"):
            if self._log_path is not None and old == self._log_path:
                continue
            try:
                old.unlink()
            except OSError:
                pass                        # 다른 프로세스가 사용 중 — 무시

    def start(self) -> None:
        binary = _find_cloudflared()
        if binary is None:
            logger.warning("cloudflared 없음 — 폰 링크 없이 로컬만 서빙한다")
            return
        # 로그는 실행마다 새 파일(PID)로 — 고정 이름을 지우려 하면 이전 cloudflared 가
        # 파일을 잡고 있을 때 PermissionError 로 죽고, 지우지 않으면 **이전 실행의 주소**를
        # 읽어 죽은 터널 링크를 알림에 보낸다.
        log_path = self._state_dir / f"cloudflared-{os.getpid()}.log"
        self._log_path = log_path
        self._cleanup_old_logs()
        self._proc = subprocess.Popen(
            [str(binary), "tunnel", "--url", LOCAL_URL, "--logfile", str(log_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._detect_url, args=(log_path,), daemon=True).start()

    def _detect_url(self, log_path: Path) -> None:
        deadline = time.time() + TUNNEL_WAIT_SEC
        while time.time() < deadline:
            time.sleep(2)
            try:
                match = TUNNEL_PATTERN.search(log_path.read_bytes())
            except OSError:
                continue
            if not match:
                continue
            self.url = match.group().decode()
            # BOM 없이 기록 — BOM 이 남으면 텔레그램 링크가 깨진다.
            (self._state_dir / PUBLIC_URL_FILE).write_text(self.url, encoding="utf-8")
            logger.info("터널 주소: %s", self.url)
            return
        logger.warning("터널 주소 감지 실패(%d초) — 로컬만 서빙한다", TUNNEL_WAIT_SEC)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class WebServer:
    """uvicorn 을 데몬 스레드로 — 트레이 이벤트 루프가 메인 스레드를 잡는다."""

    def __init__(self):
        self._server = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        import uvicorn

        from app.desktop import create_desktop_app

        # log_config=None: uvicorn 기본 로깅은 stdout.isatty() 를 요구해 --noconsole
        # EXE(stdout=None)에서 기동이 죽는다. 루트 로깅(파일)으로 전파시킨다.
        config = uvicorn.Config(create_desktop_app(), host=HOST, port=PORT,
                                log_config=None, access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 20.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._server is not None and getattr(self._server, "started", False):
                return True
            time.sleep(0.3)
        return False

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True


def _tray_image():
    """트레이 아이콘 — 상승 캔들 모양을 그려서 쓴다(외부 에셋 번들 회피)."""
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (18, 20, 26, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([12, 34, 24, 54], fill=(90, 100, 120, 255))      # 눌린 캔들
    draw.line([18, 28, 18, 34], fill=(90, 100, 120, 255), width=3)
    draw.rectangle([38, 14, 50, 44], fill=(232, 72, 85, 255))       # 상승 캔들(빨강)
    draw.line([44, 8, 44, 14], fill=(232, 72, 85, 255), width=3)
    draw.line([44, 44, 44, 50], fill=(232, 72, 85, 255), width=3)
    return image


def _existing_instance_alive() -> bool:
    """이미 떠 있는 인스턴스 감지 — :8010 /api/health 응답 여부."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{LOCAL_URL}/api/health", timeout=2) as resp:
            return resp.status == 200
    except Exception:                               # noqa: BLE001  (미기동 = 정상 경로)
        return False


def _status_text(scheduler, tunnel: Tunnel) -> str:
    from app.scheduler.service import next_run_times

    times = next_run_times(scheduler)
    return (f"다음 스캔: {times.get('daily_run') or '—'}\n"
            f"폰 링크: {tunnel.url or '(터널 없음)'}")


def _setup_logging(state_dir: Path) -> None:
    """콘솔 + 파일 로깅. --noconsole EXE 는 콘솔이 없어 파일이 유일한 진단 수단이다."""
    handlers: list[logging.Handler] = [logging.FileHandler(
        state_dir / LOG_FILE, encoding="utf-8")]
    if sys.stderr is not None:                   # --noconsole 이면 stderr 가 없다
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO, handlers=handlers, force=True,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    from app.config import get_settings, load_env

    _ensure_std_streams()                        # --noconsole: stdout/stderr None 방어
    load_env()                                   # KIS/DART/텔레그램 크리덴셜
    settings = get_settings()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(settings.state_dir)

    # 단일 인스턴스 — 이미 떠 있으면 보드만 열고 빠진다. 이 가드가 없으면 두 번째
    # 실행은 포트 충돌로 ~20초 뒤 소리 없이 죽어 '실행했는데 아무 일도 없음'이 된다.
    if _existing_instance_alive():
        logger.info("이미 실행 중인 인스턴스 감지 — 보드만 열고 종료")
        webbrowser.open(LOCAL_URL)
        return 0

    from app.store.db import init_db

    init_db()                                    # 스키마 보장(멱등) + WAL

    server = WebServer()
    server.start()
    if not server.wait_ready():
        logger.error("웹서버 기동 실패")
        return 1
    logger.info("웹서버: %s", LOCAL_URL)

    tunnel = Tunnel(settings.state_dir)
    tunnel.start()

    from app.scheduler.service import build_scheduler

    scheduler = build_scheduler()
    scheduler.start()
    logger.info("스케줄러 기동 — 08:30 프리페치 / 15:18 스캔 / 10:05 채점")

    import pystray

    def on_open(_icon=None, _item=None):
        webbrowser.open(LOCAL_URL)

    def on_copy_link(_icon=None, _item=None):
        if not tunnel.url:
            return
        subprocess.run("clip", input=tunnel.url.encode("utf-8"), shell=True, check=False)

    def on_quit(icon, _item=None):
        logger.info("종료 중...")
        scheduler.shutdown(wait=False)
        tunnel.stop()
        server.stop()
        icon.stop()

    icon = pystray.Icon(
        "closing-bet", _tray_image(), "종가베팅",
        menu=pystray.Menu(
            pystray.MenuItem("보드 열기", on_open, default=True),
            pystray.MenuItem(lambda _: _status_text(scheduler, tunnel), None, enabled=False),
            pystray.MenuItem("폰 링크 복사", on_copy_link,
                             enabled=lambda _: tunnel.url is not None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", on_quit),
        ))
    on_open()                                    # 기동 시 보드 1회 열기
    icon.run()                                   # 메인 스레드 점유(트레이 루프)
    return 0


def _report_fatal(exc: BaseException) -> None:
    """치명 오류를 로그에 남기고 사용자에게 알아볼 수 있게 알린다.

    --noconsole EXE 는 예외가 그대로 터지면 원문 트레이스백 창만 뜨고 끝난다 —
    무엇이 왜 실패했는지 알 수 없어 진단이 불가능하다."""
    detail = "".join(traceback.format_exception(exc))
    try:
        from app.config import get_settings

        log_path = get_settings().state_dir / LOG_FILE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n=== FATAL ===\n{detail}\n")
        where = str(log_path)
    except Exception:                               # noqa: BLE001  (마지막 방어선)
        where = "(로그 기록 실패)"

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, f"종가베팅을 시작하지 못했습니다.\n\n{exc}\n\n자세한 로그: {where}",
            "종가베팅 오류", 0x10)
    except Exception:                               # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:                    # noqa: BLE001  (프리즌 앱 진단)
        _report_fatal(exc)
        sys.exit(1)
