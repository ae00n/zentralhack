// Per-field confidence: number in mono plus a 2px bar, 60px wide. Below 0.5 both turn --warn.
export const REVIEW_THRESHOLD = 0.5;

export default function Confidence({ value }: { value: number }) {
  const low = value < REVIEW_THRESHOLD;
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <span className="inline-flex items-center gap-2" title={`Konfidenz ${value.toFixed(2)}`}>
      <span className="relative h-[2px] w-[60px] bg-rule">
        <span className={`absolute inset-y-0 left-0 ${low ? "bg-warn" : "bg-ink"}`} style={{ width: `${pct}%` }} />
      </span>
      <span className={`font-mono text-meta ${low ? "text-warn" : ""}`}>{value.toFixed(2)}</span>
    </span>
  );
}
