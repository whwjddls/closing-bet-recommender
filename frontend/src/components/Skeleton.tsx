// 콘솔 스켈레톤 로딩(모션③) — "로딩 중…" 텍스트 대체. shimmer는 reduced-motion 존중(CSS).
// 스크린리더용 "로딩 중" 텍스트는 sr-only로 유지(정직성·접근성).
export default function Skeleton({
  lines = 1,
  width,
}: {
  lines?: number;
  width?: string;
}) {
  return (
    <div className="skeleton" data-testid="skeleton" aria-busy="true">
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          className="skeleton-line"
          data-testid="skeleton-line"
          style={width && i === lines - 1 ? { width } : undefined}
        />
      ))}
      <span className="sr-only">로딩 중…</span>
    </div>
  );
}
