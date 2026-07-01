import { useState } from 'react';

const STORAGE_KEY = 'cbr.onboarding.dismissed.v1';

function alreadyDismissed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    // localStorage 불가 환경(사생활 모드 등)에서는 매번 노출한다.
    return false;
  }
}

// 개미 온보딩 코치마크: 최초 방문 1회 노출, 닫으면 localStorage 플래그로 영구 숨김.
export default function Onboarding() {
  const [dismissed, setDismissed] = useState<boolean>(alreadyDismissed);
  if (dismissed) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      // 저장 실패해도 최소한 이번 세션에서는 숨긴다.
    }
    setDismissed(true);
  };

  return (
    <aside
      className="onboarding"
      data-testid="onboarding"
      role="note"
      aria-label="처음 사용 안내"
    >
      <div className="ob-head">
        <span className="ob-title">처음이신가요?</span>
        <button
          type="button"
          className="ob-dismiss"
          data-testid="onboarding-dismiss"
          aria-label="안내 닫기"
          onClick={dismiss}
        >
          ×
        </button>
      </div>
      <ol className="ob-steps">
        <li>
          <span className="ob-num">①</span> 색으로 등급 확인
        </li>
        <li>
          <span className="ob-num">②</span> 잠정 배지 주의
        </li>
        <li>
          <span className="ob-num">③</span> 담기 1~9
        </li>
      </ol>
      <p className="ob-foot">이 도구는 추천만, 주문 없음</p>
    </aside>
  );
}
