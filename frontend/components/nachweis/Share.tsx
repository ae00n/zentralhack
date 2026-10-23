import { formatPct } from "@/lib/format";

/** A share 0..1 as a 2px ink bar plus the percentage in mono. No warn colour: these are measured, not guessed. */
export default function Share({ value, width = 120 }: { value: number | null | undefined; width?: number }) {
  const pct = Math.max(0, Math.min(1, value ?? 0)) * 100;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative h-[2px] bg-rule" style={{ width }}>
        {value !== null && value !== undefined && (
          <span className="absolute inset-y-0 left-0 bg-ink" style={{ width: `${pct}%` }} />
        )}
      </span>
      <span className="w-10 text-right font-mono text-meta">{formatPct(value)}</span>
    </span>
  );
}
