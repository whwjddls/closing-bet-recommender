# 통합 검증 후 잔여 수정 (Remediation Status)

- 브랜치: `impl/closing-bet`
- 구현 완료: 5개 서브시스템 전부(01 데이터·02 엔진·03 백테스트·04 API/스케줄러/오케스트레이터·05 프론트), 백엔드 pytest·프론트 vitest 모두 green.
- **적대적 통합 검증**(4렌즈 finder → 회의론자 verify)에서 확인된 결함 **20개**: 유닛은 green이지만 **프로덕션 wiring이 깨짐**(목으로 가려졌던 이음새).

## ✅ Pass 1 완료 (HEAD 0ffec71) — 핵심 라이브 경로
- orchestrate_run ↔ 실제 run_pipeline/StaticCandidate/LiveQuote/EngineRow 정합(#2,3,6,7)
- EngineRow에 spark/base_flag 추가·pipeline 산출, daily_run 저장(#1,10)
- daily_run 프로덕션 seam 구현(NotImplementedError 제거)(#4,5)
- orchestrator 커버리지 분모 → pipeline coverage_pct(#15)
- get_dilution_veto arity(snapshot_at)(#19), 어댑터 engine-facing 메서드 추가(#20 부분)
- 통합테스트 2개 추가: `test_integration_wiring.py`(orchestrate_run 실제 pipeline 구동 + daily_run→/recommendations 라운드트립). pytest 233 passed.

## ⬜ Pass 2 (다음) — 프로덕션 스텁/500 + 백테스트 가드
| # | 파일 | 결함 | 수정 |
|---|---|---|---|
| 8,12 | `scheduler/scoring_job.py:40` | 모듈함수 `fetch_morning_vwap`/`overnight_scan` 미존재(ImportError) | kis_client/dart_client에 모듈 래퍼 추가 or 메서드 호출로 변경 + 실제 기본바인딩 테스트 |
| 13 | `api/stock.py:19` | `get_stock_chart` 미존재 → 500 | pykrx_client에 `get_stock_chart(code,run_date)->{candles,high_52w,prior_high,base_box}` 구현 + 기본 provider 테스트 |
| 11 | `api/backtest.py:19` | `load_*` 주입 없음 → 500 | 프로덕션 `load_price_panel`/`load_vwap_panel` 로더 + `get_backtest_runner` 기본 wiring + 테스트 |
| 14 | `store/db.py:22` | `init_db` 데드코드(스타트업 미호출) | `main.py` FastAPI lifespan에서 `init_db()` 호출 + 부팅 테스트 |
| 16 | `backtest/engine.py:139` | run_backtest가 시점기준 재구성 우회 + `survivorship_source=True` 기본 | point-in-time/universe·guard_final_dates 경유, survivorship 기본 True 금지, n_picks 재구성 기준 |
| 9 | `scheduler/premarket.py:73` | prefetch_final FINAL 번들 폐기 | FINAL(H_ref/ATR/avg_value/D-1수급)을 UniverseCache/FINAL 캐시에 저장 → orchestrate_run이 로드해 StaticCandidate 구성 |

## ⬜ Pass 3 (nits)
| # | 파일 | 결함 | 수정 |
|---|---|---|---|
| 17 | `api/recommendations.py:14` | 백엔드 `badges` 직렬화되나 프론트는 자체 `deriveBadges` 사용(중복) | 한쪽으로 통일(백엔드 badges 제거 or 프론트가 r.badges 렌더) |
| 18 | `frontend/src/api/client.ts:66` | `session_type`/`UniverseResponse.as_of` 백엔드는 null 반환하나 타입 non-nullable | `string | null`로 + 렌더 가드 |
| 20 | `data/broker_adapter.py:89` | LiveBrokerDataAdapter가 end-to-end로 안 이어짐(Pass1서 메서드 추가됨, 확인 필요) | orchestrate_run이 실제 소비하는지 통합 확인 |

## 마무리 후
- Pass 2·3 완료 후 **적대적 검증 워크플로 재실행**(`docs/superpowers/plans/` 스크립트 참고)해 wiring 닫힘 확인.
- 그 뒤 `superpowers:finishing-a-development-branch`로 브랜치 정리(merge/PR).
