// Per-field Modell-Sicherheit: a mono percentage, "86 %". Below 0.9 (Ralph's acceptance line) it turns --warn.
// Never a bar on its own (FRONTPAGE_PLAN 2.1).
import { formatPct } from "@/lib/format";
import { SURE } from "@/lib/review";

export const REVIEW_THRESHOLD = SURE;

export default function Confidence({ value }: { value: number }) {
  const low = value < REVIEW_THRESHOLD;
  return (
    <span title={`Modell-Sicherheit ${formatPct(value)}`} className={`font-mono text-ui ${low ? "text-warn" : ""}`}>
      {formatPct(value)}
    </span>
  );
}
