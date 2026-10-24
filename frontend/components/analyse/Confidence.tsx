// Per-field Modell-Sicherheit: "86 %" in Inter with tabular numbers (FRONTPAGE_POLISH 3, rule 3).
// Below 0.9 (Ralph's acceptance line) it turns --warn. Never a bar on its own.
import { formatPct } from "@/lib/format";
import { SURE } from "@/lib/review";

export const REVIEW_THRESHOLD = SURE;

export default function Confidence({ value }: { value: number }) {
  const low = value < REVIEW_THRESHOLD;
  return (
    <span title={`Modell-Sicherheit ${formatPct(value)}`} className={`text-ui tnum ${low ? "text-warn" : "text-ink"}`}>
      {formatPct(value)}
    </span>
  );
}
