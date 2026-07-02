// 컴포넌트 간 느슨한 결합용 커스텀 이벤트 키.
// RunScanButton(GlobalHeader) 이 스캔 완료 시 발행하고, Board 가 구독해 보드를 재조회한다.
export const REFETCH_EVENT = 'closingbet:refetch';

export function emitRefetch(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(REFETCH_EVENT));
  }
}
