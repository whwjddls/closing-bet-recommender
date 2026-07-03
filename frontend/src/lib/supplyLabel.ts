// 백엔드 잠정 수급 라벨("외인▲기관▲" — kis_client.get_provisional_flows, +방향만 존재)을
// 풀네임으로 변환. 미지 포맷은 가공 없이 원문(정직성 — 추측 금지).
const KNOWN: Record<string, string> = {
  '외인▲기관▲': '외국인+ 기관+',
  '외인▲': '외국인+',
  '기관▲': '기관+',
};

export function formatSupplyToday(label: string | null | undefined): string {
  if (!label) return '—';
  return KNOWN[label] ?? label;
}
