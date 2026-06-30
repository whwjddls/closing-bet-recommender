import type { HealthResponse } from '../api/client';

export default function HealthBadge({ health }: { health: HealthResponse }) {
  return (
    <span
      data-testid="health-badge"
      data-status={health.status}
      className={`health health-${health.status.toLowerCase()}`}
    >
      <strong>{health.status}</strong>
      <span> 커버리지 {health.kis_coverage_pct}%</span>
      {health.reason && <span> · {health.reason}</span>}
    </span>
  );
}
