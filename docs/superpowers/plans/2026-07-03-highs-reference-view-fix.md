# 신고가 위젯 → 종목 상세 빈 화면 수정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "1년 최고가 근접" 위젯에서 어떤 종목을 클릭해도 종목 상세 화면이 항상 의미 있게 나오도록 3층(위젯 소스·백엔드 참고 조회·프론트 렌더링)을 수정한다.

**Architecture:** ① `/highs`가 KIS 랭킹 응답을 KRX 상장주식 목록과 교차검증해 ETF·ETN·채권펀드를 제거하고, ② `/stock/{code}` 참고 조회가 실제 종목명을 조회하며(현재 `name=code` 하드코딩), ③ 프론트는 캔들 0개일 때 흰 차트 캔버스 대신 정직한 placeholder를 그리고, 차트를 다크/라이트 테마·한국 관례색(상승 빨강/하락 파랑)으로 렌더한다.

**Tech Stack:** FastAPI + pykrx(KRX 로그인 필요) / React18 + lightweight-charts **4.2.3**(v4 API) + vitest.

---

## 0. 배경 — 실측으로 확정한 근본 원인 (2026-07-03 장중 조사)

증상: 신고가 위젯에서 `000117` 클릭 → 상세 화면이 흰 빈 차트·현재가 0·종목명 미표시·전 위젯 placeholder.

| # | 실측 증거 | 결론 |
|---|---|---|
| 1 | `curl /stock/000117` → `candles:[] · high_52w:0 · price_provisional:0.0 · name:"000117"` | 참고 모드가 빈 데이터를 그대로 직렬화 |
| 2 | `curl /stock/005930`(추천 이력 없음) → 캔들·가격(마지막 종가) 정상, **`name:"005930"`** | 차트 파이프라인은 정상. **name=code 하드코딩은 전 종목 버그** (`backend/app/api/stock.py:48`) |
| 3 | pykrx `get_market_ticker_name('000117')` → **빈 DataFrame** (005930→'삼성전자', 122350→'삼기'는 정상 문자열) | 000117은 KRX **상장 주식이 아님**(ETF/ETN 계열) → 주식용 OHLCV가 빈 값을 주는 게 당연 |
| 4 | `curl /highs` → RISE 회사채액티브·TIGER 단기채권·KIWOOM 독일DAX… **채권/지수 ETF 다수** | KIS TR `FHPST01870000`(near-new-highlow)이 **전 상품 무필터** 반환 (`kis_client.py:239-244`의 `FID_TRGT_EXLS_CLS_CODE:""`) |
| 5 | 프론트 `StockDetail.tsx`: 캔들 0개여도 `createChart` 실행 → lightweight-charts 기본 **흰 배경** 캔버스 | 다크 테마에 흰 빈 박스. 데이터 있어도 배경/캔들색이 테마·한국 관례와 불일치(기본: 상승 청록/하락 빨강) |

원인 사슬: **④ 무필터 ETF 노출 → ③ ETF는 pykrx 주식 API 미지원(빈 캔들) → ① 백엔드가 0/코드로 스텁 → ⑤ 프론트가 그대로 렌더.**

### 설계 선택 근거
- **필터는 KRX 교차검증 방식**: KIS TR의 `FID_TRGT_EXLS_CLS_CODE` 파라미터로도 거를 수 있을 가능성이 있으나 문서가 불명확 — 운영노트 #3 "실 API 필드는 반드시 실측 후 사용"(목 기반 개발로 3번 깨진 이력) 원칙에 따라, 이미 검증된 pykrx `get_market_ticker_list`(코드베이스에서 2곳 사용 중)로 교차검증한다.
- **fail-open**: KRX 목록 조회 실패/빈 값이면 원본 유지 — 필터 장애로 위젯이 통째로 비는 것보다 잡음 섞인 목록이 낫다(기존 graceful 철학과 일치).
- **price_provisional 계약 유지**: 스키마의 `float`(비옵셔널)을 바꾸지 않고, 캔들 없으면 0.0 유지 → 0은 유효 주가가 아니므로 프론트가 "—" 표기 센티널로 사용.

### 스코프 아웃 (이번에 안 함)
- KIS TR 파라미터 기반 필터(실측 필요 — 백로그), `/news`의 ETF 대응, 참고 모드에 KIS 실시간 현재가 연동(마지막 종가로 충분).

### 운영 지뢰 (실행 전 숙지)
- pykrx는 **KRX 로그인 필수**(`backend/.env`의 `KRX_ID/KRX_PW` 자동 로드, 로그인 로그 stdout 출력은 무해).
- 사용자의 uvicorn이 `--reload`로 떠 있음 — 백엔드 파일 저장 즉시 자동 재시작(KIS 토큰은 파일 캐시라 무해).
- `/highs` 첫 호출은 KRX 상장목록 1회 조회로 **2~5초** 걸림(이후 프로세스 내 당일 캐시). 프론트 위젯 로딩 상태가 흡수.
- 테스트에서 pykrx **네트워크 누출 금지** — 새 DI(name provider)를 오버라이드하지 않으면 기존 참고 모드 테스트가 실 KRX를 때리게 된다(Task 3에서 기존 테스트 수정 필수).
- 백엔드 게이트: `cd backend && .venv/Scripts/python -m pytest -q`. 프론트 게이트: `npm test` · `npx tsc --noEmit`(**`tsc -b` 금지**) · `find src -name '*.js'`=0.

---

## Task 0: 선행 미커밋 변경 커밋 (전제조건)

**Files:** 없음(git 조작만)

현재 트리에는 이 계획과 **파일이 겹치는** 미커밋 선행 작업(WORK-PLAN §1 4과업 + 상단바 UX 정리: `StockDetail.tsx`, `lib/theme.ts`, `theme.css`, `api/client.ts` 등)이 있다. 이 계획의 커밋에 섞이지 않도록 먼저 커밋한다.

- [ ] **Step 0-1: 트리 확인**

Run: `git status --short`
Expected: `.omc/` 외 전부 이 계획과 무관한 선행 작업 파일(frontend 18수정+6신규)

- [ ] **Step 0-2: 선행 작업 일괄 커밋** (파일이 과업 간 겹쳐 원자 분리 불가 — 사용자가 분할을 원하면 사용자 지시 우선)

```bash
git add frontend/src
git commit -m "feat(frontend): WORK-PLAN §1 4과업(스캔UX·dataCache·성과카드·테마토글) + 상단바 정리(배너·스캔칩·마감앵커)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 커밋 후 `git status --short` 에 frontend 변경 없음(`.omc/`는 무시 — 운영 상태 디렉터리)

---

## Task 1: pykrx 상장주식 집합·종목명 헬퍼

**Files:**
- Modify: `backend/app/data/pykrx_client.py` (파일 끝에 추가)
- Test: `backend/tests/test_pykrx_client.py` (파일 끝에 추가)

이 파일의 기존 철학을 따른다: *"pykrx 모듈은 주입 → 네트워크 없는 단위테스트"* (모든 신규 함수에 `pykrx_module` 주입 파라미터).

- [ ] **Step 1-1: 실패하는 테스트 작성** — `backend/tests/test_pykrx_client.py` 끝에 추가:

```python
# ── 상장주식 집합·종목명 헬퍼(신고가 위젯 빈 화면 수정) ──────────────────


class _FakePykrxListing:
    """상장목록/종목명용 주입형 가짜 pykrx — 네트워크 없음."""

    def __init__(self, tickers=("005930", "122350"), names=None, boom=False):
        self._tickers = list(tickers)
        self._names = names if names is not None else {"005930": "삼성전자"}
        self._boom = boom

    def get_market_ticker_list(self, day_s, market):
        if self._boom:
            raise ConnectionError("KRX outage")
        return list(self._tickers)

    def get_market_ticker_name(self, ticker):
        if self._boom:
            raise ConnectionError("KRX outage")
        # 실측: 미상장 티커(ETF 등)는 문자열이 아니라 빈 DataFrame 을 반환한다
        return self._names.get(ticker, pd.DataFrame())


def _clear_listing_caches():
    pykrx_client._LISTED_CACHE.clear()
    pykrx_client._NAME_CACHE.clear()


def test_filter_listed_stocks_drops_non_stocks():
    _clear_listing_caches()
    rows = [{"ticker": "005930", "name": "삼성전자"},
            {"ticker": "000117", "name": "어떤채권ETF"}]
    out = pykrx_client.filter_listed_stocks(rows, pykrx_module=_FakePykrxListing())
    assert [r["ticker"] for r in out] == ["005930"]
    _clear_listing_caches()


def test_filter_listed_stocks_fail_open_on_error_and_empty():
    _clear_listing_caches()
    rows = [{"ticker": "000117", "name": "어떤채권ETF"}]
    # KRX 조회 실패 → 원본 유지(fail-open)
    assert pykrx_client.filter_listed_stocks(
        rows, pykrx_module=_FakePykrxListing(boom=True)) == rows
    # 빈 상장목록(휴장 등) → 원본 유지
    assert pykrx_client.filter_listed_stocks(
        rows, pykrx_module=_FakePykrxListing(tickers=())) == rows
    _clear_listing_caches()


def test_listed_stock_set_caches_per_day():
    _clear_listing_caches()
    day_s = "20260703"
    first = pykrx_client.listed_stock_set(day_s, pykrx_module=_FakePykrxListing())
    assert "005930" in first
    # 두 번째 호출은 캐시 히트 — 장애 모듈을 줘도 네트워크(예외) 안 탄다
    second = pykrx_client.listed_stock_set(day_s, pykrx_module=_FakePykrxListing(boom=True))
    assert second == first
    _clear_listing_caches()


def test_stock_name_resolves_and_none_for_unlisted():
    _clear_listing_caches()
    px = _FakePykrxListing()
    assert pykrx_client.stock_name("005930", pykrx_module=px) == "삼성전자"
    assert pykrx_client.stock_name("000117", pykrx_module=px) is None   # 빈 DataFrame → None
    # 캐시 히트 — 장애 모듈을 줘도 이미 캐시된 이름 반환
    assert pykrx_client.stock_name(
        "005930", pykrx_module=_FakePykrxListing(boom=True)) == "삼성전자"
    _clear_listing_caches()
```

(파일 상단에 `import pandas as pd`, `import app.data.pykrx_client as pykrx_client` 가 이미 있는지 확인 — 없으면 추가.)

- [ ] **Step 1-2: 실패 확인**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_pykrx_client.py -q -k "listed or stock_name"`
Expected: FAIL — `AttributeError: ... has no attribute 'filter_listed_stocks'`

- [ ] **Step 1-3: 구현** — `backend/app/data/pykrx_client.py` 파일 끝에 추가:

```python
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
```

- [ ] **Step 1-4: 통과 확인**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_pykrx_client.py -q`
Expected: 파일 전체 PASS (기존 테스트 포함)

- [ ] **Step 1-5: 커밋**

```bash
git add backend/app/data/pykrx_client.py backend/tests/test_pykrx_client.py
git commit -m "feat(data): KRX 상장주식 집합·종목명 헬퍼 — 당일 캐시·fail-open·모듈 주입

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: /highs 비주식 필터 와이어링

**Files:**
- Modify: `backend/app/api/highs.py:10-16` (`get_highs_provider`)
- Test: `backend/tests/api/test_highs.py` (파일 끝에 추가)

기존 라우트 테스트 3개는 provider를 오버라이드하므로 영향 없음. 필터는 **기본 provider 안**에 넣는다(라우트에 별도 DI를 추가하면 기존 테스트들이 실 KRX 네트워크를 타게 됨).

- [ ] **Step 2-1: 실패하는 테스트 작성** — `backend/tests/api/test_highs.py` 끝에 추가:

```python
import datetime as dt

import app.data.kis_client as kis_client
import app.data.pykrx_client as pykrx_client


def test_default_provider_filters_non_stocks(monkeypatch):
    # 기본 provider = KIS near-new-highlow ∩ KRX 상장주식. 두 외부 IO 모두 스텁.
    class _StubKis:
        def get_near_new_highs(self):
            return [{"ticker": "005930", "name": "삼성전자"},
                    {"ticker": "000117", "name": "어떤채권ETF"}]

    monkeypatch.setattr(kis_client, "build_default_client", lambda: _StubKis())
    day_s = (dt.date.today()).strftime("%Y%m%d")
    pykrx_client._LISTED_CACHE[day_s] = frozenset({"005930"})
    try:
        rows = get_highs_provider()()
    finally:
        pykrx_client._LISTED_CACHE.clear()
    assert [r["ticker"] for r in rows] == ["005930"]     # ETF(000117) 제거됨
```

- [ ] **Step 2-2: 실패 확인**

Run: `cd backend && .venv/Scripts/python -m pytest tests/api/test_highs.py -q`
Expected: 신규 테스트 FAIL — rows에 000117이 남아 있음 (`['005930', '000117'] != ['005930']`)

- [ ] **Step 2-3: 구현** — `backend/app/api/highs.py`의 `get_highs_provider`를 다음으로 교체:

```python
def get_highs_provider() -> Callable:
    """신고가 근접 '주식' 공급자 = KIS near-new-highlow ∩ KRX 상장주식.

    KIS 랭킹은 ETF·ETN·채권펀드를 섞어 주는데(실측 2026-07-03), 이들은 전략
    대상이 아니고 pykrx 주식 API가 지원하지 않아 클릭 시 빈 화면이 된다 → 필터.
    테스트는 dependency_overrides 로 주입. 지연 임포트 — 네트워크는 호출 때만."""
    def _provider() -> list[dict]:
        from app.data.kis_client import build_default_client
        from app.data.pykrx_client import filter_listed_stocks
        return filter_listed_stocks(build_default_client().get_near_new_highs())
    return _provider
```

- [ ] **Step 2-4: 통과 확인**

Run: `cd backend && .venv/Scripts/python -m pytest tests/api/test_highs.py -q`
Expected: 4개 전부 PASS

- [ ] **Step 2-5: 커밋**

```bash
git add backend/app/api/highs.py backend/tests/api/test_highs.py
git commit -m "fix(highs): 신고가 근접에서 ETF·ETN 제외 — KRX 상장주식 교차검증

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: /stock 참고 모드 종목명 조회 (name=code 하드코딩 제거)

**Files:**
- Modify: `backend/app/api/stock.py` (DI 추가 + 참고 분기 1줄)
- Test: `backend/tests/api/test_stock.py:91-102` (기존 참고 모드 테스트 **수정 필수**) + 신규 1개

⚠️ **기존 테스트 수정이 선행**: name provider DI를 추가하면 기존 `test_stock_reference_mode_when_no_recommendation`이 오버라이드 없이는 기본 provider(실 pykrx 네트워크)를 타게 된다.

- [ ] **Step 3-1: 실패하는 테스트 작성** — `test_stock.py`의 임포트에 `get_name_provider` 추가 후, 기존 참고 모드 테스트를 수정하고 폴백 테스트를 신설:

```python
from app.api.stock import get_chart_provider, get_name_provider    # 임포트 갱신
```

기존 `test_stock_reference_mode_when_no_recommendation`에 2줄 추가/1줄 추가:

```python
def test_stock_reference_mode_when_no_recommendation(client):
    # 추천 이력 없는 종목(신고가 근접 위젯 진입 등) → 404 대신 참고 조회:
    # 차트/갭/수급은 제공, 추천 전용 필드(grade/final/contributions)는 None/빈 값.
    client.app.dependency_overrides[get_chart_provider] = lambda: _fake_chart
    client.app.dependency_overrides[get_name_provider] = (
        lambda: (lambda code: "테스트종목"))               # 실 KRX 네트워크 차단
    resp = client.get("/stock/999999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["grade"] is None and body["final"] is None
    assert body["contributions"] == {}
    assert body["ticker"] == "999999"
    assert body["name"] == "테스트종목"                    # name=code 하드코딩 제거 검증
    assert len(body["candles"]) == 2
    assert body["price_provisional"] == 109.0          # 마지막 종가로 현재가 대체
```

신규 테스트(같은 파일 끝):

```python
def test_stock_reference_mode_name_falls_back_to_code(client):
    # 종목명 조회 실패/미상장(None) → 코드 폴백(빈 이름 금지)
    client.app.dependency_overrides[get_chart_provider] = lambda: _fake_chart
    client.app.dependency_overrides[get_name_provider] = lambda: (lambda code: None)
    body = client.get("/stock/999999").json()
    assert body["name"] == "999999"
```

- [ ] **Step 3-2: 실패 확인**

Run: `cd backend && .venv/Scripts/python -m pytest tests/api/test_stock.py -q`
Expected: FAIL — `ImportError: cannot import name 'get_name_provider'`

- [ ] **Step 3-3: 구현** — `backend/app/api/stock.py`:

`get_chart_provider` 아래에 추가:

```python
def get_name_provider() -> Callable:
    """종목명 공급자(KRX). 참고 조회(추천 이력 없음) 응답의 name 채움용.
    테스트는 dependency_overrides 로 주입. 지연 임포트 — 추천 이력이 있으면
    (rec.name 사용) pykrx 네트워크가 발생하지 않는다."""
    def _resolver(code: str) -> str | None:
        from app.data.pykrx_client import stock_name
        return stock_name(code)
    return _resolver
```

`get_stock` 시그니처에 DI 추가:

```python
def get_stock(code: str, on: date | None = None, db: Session = Depends(get_db),
              chart: Callable = Depends(get_chart_provider),
              namer: Callable = Depends(get_name_provider)) -> StockDetailResponse:
```

참고 분기(`if rec is None:`)의 응답 1줄 변경:

```python
        return StockDetailResponse(
            ticker=code, name=namer(code) or code, price_provisional=last_close,
```

- [ ] **Step 3-4: 통과 확인**

Run: `cd backend && .venv/Scripts/python -m pytest tests/api/test_stock.py -q`
Expected: 7개 전부 PASS (기존 6 + 신규 1)

- [ ] **Step 3-5: 백엔드 전체 게이트**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: 310+ 전부 PASS (다른 라우트로의 회귀 없음 — namer는 참고 분기에서만 호출되므로 추천 이력 있는 기존 테스트는 영향 없음)

- [ ] **Step 3-6: 커밋**

```bash
git add backend/app/api/stock.py backend/tests/api/test_stock.py
git commit -m "fix(stock): 참고 조회 종목명 KRX 조회 — name=code 하드코딩 제거

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: 프론트 — 빈 캔들 placeholder + 현재가 0·이름 중복 가드

**Files:**
- Modify: `frontend/src/pages/StockDetail.tsx`
- Modify: `frontend/src/styles/theme.css` (`.sd-chart-empty` 추가)
- Test: `frontend/src/pages/StockDetail.test.tsx`

- [ ] **Step 4-1: 실패하는 테스트 작성** — `StockDetail.test.tsx` 끝에 추가:

```tsx
const referenceEmpty: StockDetailResponse = {
  ticker: '000117',
  name: '000117',            // 백엔드 이름 조회 실패 시 코드 폴백 케이스
  price_provisional: 0,      // 캔들 없음 → 0 센티널
  grade: null,
  final: null,
  candles: [],
  high_52w: 0,
  prior_high: 0,
  base_box: null,
  contributions: {},
  overnight_gap: null,
  supply_5d: null,
};

describe('참고 조회 빈 데이터 가드', () => {
  it('캔들이 없으면 차트 캔버스 대신 placeholder(흰 박스 금지)', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(referenceEmpty);
    renderAt('000117');
    await waitFor(() =>
      expect(screen.getByTestId('daily-chart-empty')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('daily-chart')).not.toBeInTheDocument();
    expect(createChart).not.toHaveBeenCalled();
  });

  it('현재가 0은 —로 표기하고 잠정 워터마크를 숨긴다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(referenceEmpty);
    renderAt('000117');
    await waitFor(() =>
      expect(screen.getByTestId('daily-chart-empty')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('sd-price')).toHaveTextContent('—');
    expect(screen.queryByTestId('provisional-watermark')).not.toBeInTheDocument();
  });

  it('종목명이 코드와 같으면 코드 중복 표기를 생략한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(referenceEmpty);
    renderAt('000117');
    await waitFor(() =>
      expect(screen.getByTestId('daily-chart-empty')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('sd-code')).not.toBeInTheDocument();
  });

  it('정상 종목은 코드 병기를 유지한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() => expect(screen.getByTestId('sd-code')).toBeInTheDocument());
  });
});
```

- [ ] **Step 4-2: 실패 확인**

Run: `cd frontend && npx vitest run src/pages/StockDetail.test.tsx`
Expected: 신규 4개 FAIL (`daily-chart-empty` 미존재 / `sd-code` testid 미존재)

- [ ] **Step 4-3: 구현** — `StockDetail.tsx`:

(a) 차트 영역 JSX 교체 — `<div ref={chartRef} data-testid="daily-chart" className="sd-chart" />` 를:

```tsx
          {detail.candles.length > 0 ? (
            <div ref={chartRef} data-testid="daily-chart" className="sd-chart" />
          ) : (
            <p className="sd-chart-empty card" data-testid="daily-chart-empty">
              차트 데이터 없음 — 주식이 아닌 종목(ETF 등)이거나 거래 이력이 없어요
            </p>
          )}
```

(b) 차트 effect 가드 — `if (!detail || !chartRef.current) return;` 을:

```tsx
    if (!detail || detail.candles.length === 0 || !chartRef.current) return;
```

(c) 현재가 표기 — `sd-metric-val` 내용을:

```tsx
            <span className="sd-metric-val mono" data-testid="sd-price">
              {detail.price_provisional > 0 ? (
                <>
                  {formatPrice(detail.price_provisional)}
                  <sup
                    data-testid="provisional-watermark"
                    className="sd-prov"
                    title="15:20 기준 값 — 마감(15:30) 때 바뀔 수 있어요"
                  >
                    15:20 기준
                  </sup>
                </>
              ) : (
                '—'
              )}
            </span>
```

(d) 이름·코드 중복 가드 — `sd-name` h1 내부를:

```tsx
          <h1 className="sd-name">
            {detail.name}
            {detail.name !== detail.ticker && (
              <span className="sd-code mono" data-testid="sd-code">
                {detail.ticker}
              </span>
            )}
          </h1>
```

(e) `theme.css`의 `.sd-chart` 블록 아래 추가:

```css
/* 캔들 없는 종목(ETF 등 참고 조회) — 흰 캔버스 대신 정직한 placeholder */
.sd-chart-empty {
  margin: 0;
  padding: var(--sp-6) var(--sp-4);
  text-align: center;
  color: var(--text-lo);
  font-size: 12.5px;
}
```

- [ ] **Step 4-4: 통과 확인**

Run: `cd frontend && npx vitest run src/pages/StockDetail.test.tsx`
Expected: 전부 PASS (기존 7 + 신규 4)

- [ ] **Step 4-5: 커밋**

```bash
git add frontend/src/pages/StockDetail.tsx frontend/src/pages/StockDetail.test.tsx frontend/src/styles/theme.css
git commit -m "fix(frontend): 종목상세 빈 캔들 placeholder + 현재가0·이름중복 가드

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: 프론트 — 일봉 차트 테마 적용 + 테마 전환 시 재도색

**Files:**
- Modify: `frontend/src/lib/theme.ts` (`THEME_EVENT` 추가)
- Modify: `frontend/src/pages/StockDetail.tsx` (차트 옵션 + 이벤트 구독)
- Test: `frontend/src/lib/theme.test.ts`, `frontend/src/pages/StockDetail.test.tsx`

lightweight-charts **4.2.3**(v4 API) — 배경은 `layout.background: { type: ColorType.Solid, color }` 형식. canvas라 CSS 변수가 자동 적용되지 않으므로 기존 `themeColor()` 헬퍼(StockDetail.tsx에 있음)로 생성 시점 토큰을 읽고, 테마 전환 이벤트에 차트를 재생성한다. 캔들색은 한국 관례(상승 `--up` 빨강 / 하락 `--down` 파랑) — 라이브러리 기본값(상승 청록/하락 빨강)은 앱 전체 색 언어와 정반대.

- [ ] **Step 5-1: 실패하는 테스트 작성**

`theme.test.ts` 끝에 추가 (임포트에 `THEME_EVENT`, `vi` 추가):

```ts
it('applyTheme는 THEME_EVENT를 발행한다(canvas 차트 재도색용)', () => {
  const seen = vi.fn();
  window.addEventListener(THEME_EVENT, seen);
  applyTheme('light');
  expect(seen).toHaveBeenCalledTimes(1);
  window.removeEventListener(THEME_EVENT, seen);
});
```

`StockDetail.test.tsx` — vi.hoisted 목에 `addCandlestickSeries` 노출 + `ColorType` 목 추가:

```tsx
const { createChart, setData, createPriceLine, addCandlestickSeries } = vi.hoisted(() => {
  const setData = vi.fn();
  const createPriceLine = vi.fn();
  const candleSeries = { setData, createPriceLine };
  const addCandlestickSeries = vi.fn(() => candleSeries);
  const createChart = vi.fn(() => ({
    addCandlestickSeries,
    remove: vi.fn(),
    timeScale: () => ({ fitContent: vi.fn() }),
  }));
  return { createChart, setData, createPriceLine, addCandlestickSeries };
});
vi.mock('lightweight-charts', () => ({
  createChart,
  CrosshairMode: {},
  ColorType: { Solid: 'solid' },
}));
```

테스트 추가 (임포트: `import { act } from '@testing-library/react'`, `import { THEME_EVENT } from '../lib/theme'`):

```tsx
describe('차트 테마', () => {
  it('테마 전환 이벤트가 오면 차트를 다시 그린다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() => expect(createChart).toHaveBeenCalledTimes(1));
    act(() => {
      window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: 'light' }));
    });
    await waitFor(() => expect(createChart).toHaveBeenCalledTimes(2));
  });

  it('캔들색은 한국 관례(상승/하락) 옵션으로 지정한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() => expect(addCandlestickSeries).toHaveBeenCalled());
    expect(addCandlestickSeries).toHaveBeenCalledWith(
      expect.objectContaining({
        upColor: expect.any(String),
        downColor: expect.any(String),
      }),
    );
  });
});
```

- [ ] **Step 5-2: 실패 확인**

Run: `cd frontend && npx vitest run src/lib/theme.test.ts src/pages/StockDetail.test.tsx`
Expected: FAIL — `THEME_EVENT` 미export / 재생성 안 됨 / addCandlestickSeries 인자 없음

- [ ] **Step 5-3: 구현**

`lib/theme.ts` — `applyTheme` 교체 + 상수 추가:

```ts
// 테마 변경 브로드캐스트 — canvas 차트(lightweight-charts)는 CSS 변수가
// 자동 적용되지 않아, 구독 컴포넌트가 현재 토큰으로 다시 그린다.
export const THEME_EVENT = 'closingbet:theme';

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}
```

`StockDetail.tsx` — 임포트 교체/추가:

```tsx
import { createChart, ColorType } from 'lightweight-charts';
import { THEME_EVENT } from '../lib/theme';
```

컴포넌트에 구독 state/effect 추가(`detail` state 선언 아래):

```tsx
  // 테마 전환 시 차트 재생성 트리거(canvas는 CSS 변수 미적용).
  const [themeEpoch, setThemeEpoch] = useState(0);

  useEffect(() => {
    const bump = () => setThemeEpoch((v) => v + 1);
    window.addEventListener(THEME_EVENT, bump);
    return () => window.removeEventListener(THEME_EVENT, bump);
  }, []);
```

차트 effect — createChart 옵션·시리즈 옵션·deps 교체:

```tsx
  useEffect(() => {
    if (!detail || detail.candles.length === 0 || !chartRef.current) return;
    const chart = createChart(chartRef.current, {
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: themeColor('--bg-1', '#141922') },
        textColor: themeColor('--text-mid', '#9da7b3'),
      },
      grid: {
        vertLines: { color: themeColor('--border', '#2a3441') },
        horzLines: { color: themeColor('--border', '#2a3441') },
      },
    });
    // 기존 priceLine용 상수(upColor/downColor/flatColor — 이미 effect 상단에 선언돼
    // 있음)를 그대로 재사용한다. 새 변수를 중복 선언하지 말 것.
    const series = chart.addCandlestickSeries({
      upColor,
      downColor,
      borderUpColor: upColor,
      borderDownColor: downColor,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });
    // …(기존 upColor/downColor/flatColor 선언과 setData·priceLines·fitContent 그대로)…
    return () => chart.remove();
  }, [detail, themeEpoch]);
```

- [ ] **Step 5-4: 통과 확인 + 프론트 전체 게이트**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npx vite build`
Expected: 전 테스트 PASS · tsc 출력 없음 · `✓ built`

Run: `find frontend/src -name '*.js' | wc -l`
Expected: `0`

- [ ] **Step 5-5: 커밋**

```bash
git add frontend/src/lib/theme.ts frontend/src/lib/theme.test.ts frontend/src/pages/StockDetail.tsx frontend/src/pages/StockDetail.test.tsx
git commit -m "feat(frontend): 일봉 차트 테마 적용 — 다크/라이트 배경·그리드 + 한국 관례 캔들색

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: 라이브 검증 (uvicorn --reload 자동 반영)

**Files:** 없음(검증만). @superpowers:verification-before-completion

- [ ] **Step 6-1: 참고 조회 이름 확인**

Run: `curl -s localhost:8010/stock/005930 | python -c "import json,sys; d=json.load(sys.stdin); print(d['name'], d['price_provisional'], len(d['candles']))"`
Expected: `삼성전자 <양수> <60내외>` — name이 더 이상 코드가 아님 (첫 호출은 KRX 로그인으로 수 초 소요 가능)

- [ ] **Step 6-2: /highs ETF 제거 확인**

Run: `curl -s localhost:8010/highs | python -c "import json,sys; [print(i['ticker'], i['name']) for i in json.load(sys.stdin)['items']]"`
Expected: 채권/지수 ETF(RISE·TIGER·KODEX·PLUS·HANARO 등 브랜드) 미출현, 일반 주식만. 첫 호출 2~5초. (장 시간대에 따라 빈 목록일 수 있음 — 빈 목록이면 위젯 placeholder가 정상)

- [ ] **Step 6-3: 브라우저 확인** (localhost:5173)

1. 보드 → "1년 최고가 근접" 위젯 → 아무 종목 클릭 → 상세에 **실제 종목명·차트(다크 배경·상승 빨강/하락 파랑 캔들)·현재가** 표시 확인
2. ☀️/🌙 토글 → 차트 배경·글자·캔들색이 즉시 전환되는지 확인
3. (선택) 주소창에 `/stock/000117` 직접 입력 → "차트 데이터 없음" placeholder + 현재가 "—" 확인 (위젯에서는 더 이상 진입 불가하지만 URL 직접 진입은 여전히 가능)

- [ ] **Step 6-4: WORK-PLAN 반영** — `docs/superpowers/WORK-PLAN.md` §5(완료된 것)에 한 줄 추가 후 커밋:

```
- 신고가 위젯 빈 화면 수정: /highs ETF 필터(KRX 교차검증) · 참고 조회 실명 · 차트 테마/빈데이터 가드 (2026-07-03)
```

```bash
git add docs/superpowers/WORK-PLAN.md docs/superpowers/plans/2026-07-03-highs-reference-view-fix.md
git commit -m "docs: 신고가 빈 화면 수정 계획·완료 기록

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 참고 — 예상 소요·순서 의존성

| Task | 내용 | 의존 | 예상 |
|---|---|---|---|
| 0 | 선행 작업 커밋 | — | 5분 |
| 1 | pykrx 헬퍼 | — | 30분 |
| 2 | /highs 필터 | 1 | 15분 |
| 3 | /stock 이름 | 1 | 20분 |
| 4 | 프론트 빈데이터 가드 | — (백엔드와 독립) | 30분 |
| 5 | 차트 테마 | 4 | 30분 |
| 6 | 라이브 검증 | 1–5 | 15분 |
