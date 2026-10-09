/** Bounded local diagnostics. No document text or metrics leave this browser. */
type Metric = { stage: string; duration_ms: number; recorded_at: number };
const samples: Metric[] = [];
export function recordMetric(stage: string, duration: number) {
  samples.push({
    stage,
    duration_ms: Math.round(duration * 1000) / 1000,
    recorded_at: Date.now(),
  });
  if (samples.length > 100) samples.shift();
}
export function performanceSnapshot() {
  return [...samples];
}
Object.assign(window, { lumiPerformance: performanceSnapshot });
