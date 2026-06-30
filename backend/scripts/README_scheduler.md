# Windows 작업스케줄러 운영

## 등록
관리자 PowerShell:
```
.\scripts\register_tasks.ps1 -PythonExe "C:\Python314\python.exe" -BackendDir "D:\work\git\closing-bet-recommender\backend"
```

## 3개 잡
| 잡 | 모듈 | 시각 | 책임 |
|---|---|---|---|
| CBR-Premarket | `python -m app.scheduler.premarket` | 08:30 | FINAL prefetch + 헬스체크(실패→fail-closed) |
| CBR-DailyRun  | `python -m app.scheduler.daily_run` | 15:18 | 거래일·세션 판정 후 15:20 스냅샷 파이프라인, 커버리지<70%→미발행, top3 알림 |
| CBR-Scoring   | `python -m app.scheduler.scoring_job` | 09:05 | 전 거래일 픽 채점(확정종가·오전VWAP·N/A) + DART 오버나잇 재스캔 |

## 운영 메모
- 각 모듈은 `TradingCalendar`로 거래일/특수세션을 자체 판정 → 휴장일엔 즉시 종료.
- 특수세션(조기폐장)은 캘린더 마감−10분으로 스냅샷 자동 시프트.
- PC 절전/네트워크 끊김 시 그날 추천 없음(미스). `-WakeToRun`으로 절전 복귀 시도.
- 발행 게이트(보드 '완료'): ① 15:20–15:30 창 내 ② 커버리지≥70% ③ 룩어헤드/풀-재현 가드 그린.
- 해제: `Unregister-ScheduledTask -TaskName 'CBR-Premarket','CBR-DailyRun','CBR-Scoring' -Confirm:$false`
