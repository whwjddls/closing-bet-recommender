"""daily_run 운영 seam — 라이브 pykrx/KIS/DART 클라이언트 + LiveBrokerDataAdapter +
store 페이사드를 조립해 ``orchestrate_run`` 을 바인딩한다 (00 §3).

모든 무거운/네트워크 의존(pykrx, requests)은 함수 내부에서 지연 임포트한다 —
모듈 임포트만으로 테스트가 깨지지 않게 한다(테스트는 run_pipeline 을 주입).
크리덴셜은 환경변수에서 읽고, 미설정 시 fail-closed 로 명시적으로 실패한다.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta

from app.data.mapping import Market

KIS_DEFAULT_BASE_URL = "https://openapi.koreainvestment.com:9443"
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
LOOKBACK_DAYS = 400


class _RealClock:
    """KIS 레이트버짓/토큰 만료용 실 시계."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"운영 seam 크리덴셜 미설정: 환경변수 {name} 가 필요하다(fail-closed).")
    return value


def _kis_transport(method: str, url: str, *, headers=None, json=None, params=None) -> dict:
    import requests

    resp = requests.request(method, url, headers=headers, json=json, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _dart_transport(params: dict) -> dict | None:
    import requests

    resp = requests.get(DART_LIST_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _load_corp_code_map(session_factory) -> dict[str, str]:
    from sqlalchemy import select

    from app.store.models import CorpCodeMap

    with session_factory() as db:
        rows = db.scalars(select(CorpCodeMap)).all()
        return {r.ticker: r.corp_code for r in rows if r.ticker}


def build_live_adapter():
    """실 pykrx/KIS/DART 클라이언트를 합성한 LiveBrokerDataAdapter 를 만든다."""
    from pykrx import stock as pykrx_stock

    from app.data.broker_adapter import LiveBrokerDataAdapter
    from app.data.dart_client import DartClient
    from app.data.kis_client import KisClient, KisConfig
    from app.data.pykrx_client import PykrxClient
    from app.store.db import SessionLocal

    pykrx = PykrxClient(pykrx_stock)
    kis = KisClient(
        _kis_transport, _RealClock(),
        KisConfig(
            app_key=_require_env("KIS_APP_KEY"),
            app_secret=_require_env("KIS_APP_SECRET"),
            base_url=os.environ.get("KIS_BASE_URL", KIS_DEFAULT_BASE_URL),
            account=_require_env("KIS_ACCOUNT")))
    dart = DartClient(
        _dart_transport, _load_corp_code_map(SessionLocal),
        api_key=_require_env("DART_API_KEY"))

    today = date.today()
    return LiveBrokerDataAdapter(
        pykrx, kis, dart,
        healthcheck_index_market=Market.KOSPI,
        healthcheck_fromdate=(today - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d"),
        healthcheck_todate=(today - timedelta(days=1)).strftime("%Y%m%d"),
        healthcheck_expected_last=None)


def build_live_run_pipeline():
    """``(run_date, snapshot_at) -> RunResult`` 바인딩을 반환한다(daily_run seam)."""
    from app.engine.orchestrator import orchestrate_run
    from app.store.db import SessionLocal
    from app.store.orchestrator_store import OrchestratorStore

    adapter = build_live_adapter()

    def run(run_date: date, snapshot_at: datetime):
        with SessionLocal() as db:
            store = OrchestratorStore(db)
            result = orchestrate_run(run_date, snapshot_at, adapter=adapter, store=store)
            db.commit()
            return result

    return run
