import { formatAny, formatField } from "@/lib/format";
import { FIELD_ROWS, fieldLabel } from "@/lib/labels";
import { needsReview, type AnalysisResult, type FieldKey } from "@/lib/types";
import ExportButtons from "@/components/ExportButtons";
import FieldRow from "./FieldRow";

// Rejected hypotheses on year_range belong to the Jahrzehnt row, which shows the range.
const ROW_OF: Record<string, FieldKey> = { year_range: "decade" };

export default function ResultPanel({ result }: { result: AnalysisResult }) {
  const review = needsReview(result);
  const rejected = result.rejected_hypotheses ?? [];

  return (
    <section className="fade-in">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="font-serif text-section">Ergebnis</h2>
        <p className="text-meta text-ink-muted">
          Gesamt <span className="font-mono">{result.overall_confidence.toFixed(2)}</span>
          {review && <span className="text-warn"> · Prüfung nötig</span>}
          {result.usage?.budget_hit && <span className="text-warn"> · Budget erreicht</span>}
        </p>
      </div>

      <div className="mt-2 divide-y divide-rule border-y border-rule">
        {FIELD_ROWS.map(({ key, label }) => {
          const field = result.fields[key];
          if (!field) return null;
          return (
            <FieldRow
              key={key}
              label={label}
              value={formatField(key, result)}
              confidence={field.confidence}
              evidence={field.evidence ?? []}
              rejected={rejected.filter((r) => (ROW_OF[r.field] ?? r.field) === key)}
            />
          );
        })}
      </div>

      {rejected.length > 0 && (
        <details className="group mt-3">
          <summary className="cursor-pointer text-meta text-ink-muted hover:text-ink">
            Verworfene Hypothesen ({rejected.length})
          </summary>
          <ul className="mt-2 space-y-1.5">
            {rejected.map((r, i) => (
              <li key={i} className="grid grid-cols-[88px_1fr] gap-3 text-meta">
                <span className="text-ink-muted">{fieldLabel(r.field)}</span>
                <span>
                  <span className="font-medium">{formatAny(r.value)}</span>
                  <span className="text-ink-muted">. {r.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <ExportButtons ids={[result.photo_id]} className="mt-4" />
    </section>
  );
}
