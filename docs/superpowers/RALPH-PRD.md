# Ralph PRD — 남은 위젯 전부 (2026-07-02)

기완료: P0(다크테마·등급위계·방향색·잠정배지·정직성배너·카운트다운·리스크·top3), P1(지수스트립·담기트레이·오버나잇갭·섹터히트맵+시장폭).

## 🟢 Deliverable 스토리 (지금 데이터로 구현 — pykrx/DART/기존, 키 불필요)

| ID | 스토리 | 수용기준 | pass |
|---|---|---|---|
| S1 | 성과추적 강화 | /performance+backtest에 등급별·레짐별(승률/평균/n) + MDD·손익비·연속손실 + 누적곡선 코스피벤치 + 실패픽 원인태그. 프론트 Performance 페이지 렌더. backend pytest·frontend vitest green | ☐ |
| S2 | 종목상세 강화 | /stock candles로 거래대금 히스토그램, 5승수 막대(신·거·시황·수급·재), 종목별 외인·기관 5일 누적 수급 막대. vitest green | ☐ |
| S3 | 투자자별 수급 요약 | /market에 investors{외인·기관·개인 순매수} 추가 + 프론트 위젯. green | ☐ |
| S4 | 거래 캘린더 위젯 | /calendar 엔드포인트(휴장·조기폐장·만기 네마녀·배당락 D-day) + 프론트 위젯. green | ☐ |
| S5 | 공시 일정 | /disclosures(DART 유증·CB·배당/권리락 리스트) + 프론트 위젯. green | ☐ |
| S6 | 스캐너 퍼널 + 거의들뻔 | /universe 확장(유니버스→30 퍼널 카운트 + near-miss 탈락사유) + 프론트 퍼널 뷰. green | ☐ |
| S7 | 익일 오전 청산 리마인더 | 어제 픽 + 목표/손절 + 상태. (실시간 VWAP추정은 KIS 필요 → 미연동 표기) 프론트 위젯. green | ☐ |
| S8 | 개미 온보딩 + 용어 툴팁 | 최초1회 코치마크(dismiss 영구) + 용어 `?` 호버 툴팁(RVOL/오전VWAP/등급/잠정). vitest green | ☐ |
| S9 | 데스크톱 알림 + 갱신 타임스탬프 | 브라우저 Notification(15:20 완료) + 헤더 "기준시각·데이터 나이". vitest green | ☐ |

## 🚫 Blocked (사용자 입력/외부 소스 필요 — 미구현, 보고만)
- B1 **15:20 자동 스캔 트리거** — KIS 실시간 + 스케줄러 폴링 필요(키 미연동)
- B2 **실적 발표 캘린더 + 이벤트-종목 충돌 게이트** — 실적 일정 데이터 소스 필요(무료 소스 확정 안 됨)
- B3 **청산 리마인더 실시간 오전 VWAP 추정** — KIS 분봉 필요

## 완료 게이트
전 🟢 스토리 pass + backend pytest green + frontend vitest green + tsc clean + reviewer 검증 + deslop.
