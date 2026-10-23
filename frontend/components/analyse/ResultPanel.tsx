// Erschliessung (FRONTPAGE_PLAN 5): suggested title, the brief's five fields in fixed order with
// "nicht bestimmbar", per-field Modell-Sicherheit and provenance, then the Begründung box.
import ExportButtons from "@/components/ExportButtons";
import { formatAny, formatField, formatPct, isEmptyValue } from "@/lib/format";
import { FIELD_ROWS, fieldLabel } from "@/lib/labels";
import { REVIEW_FIELDS, SURE, effectiveValue, formatValue, isCorrected, provenance, suggestedTitle } from "@/lib/review";
import { needsReview, type AnalysisResult, type FieldKey, type ReviewField } from "@/lib/types";
import FieldRow from "./FieldRow";

// Rejected hypotheses on year_range belong to the Jahrzehnt row, which shows the range.
const ROW_OF: Record<string, FieldKey> = { year_range: "decade" };

function isReviewField(key: FieldKey): key is ReviewField {
  return (REVIEW_FIELDS as string[]).includes(key);
}

export default function ResultPanel({ result }: { result: AnalysisResult }) {
  const review = needsReview(result);
  const rejected = result.rejected_hypotheses ?? [];
  const title = suggestedTitle(result);
  // The five brief fields always show (empty ones as "nicht bestimmbar"); postcard extras only when present.
  const rows = FIELD_ROWS.filter(({ key }) => isReviewField(key) || result.fields[key]);

  return (
    <section className="fade-in">
      <h2 className="text-h3">Erschliessung</h2>

      <div className="mt-3">
        <p className="text-small text-ink-muted">Titel</p>
        <p className="text-h2 font-normal">{title ?? "nicht bestimmbar"}</p>
        <p className="mt-0.5 text-meta text-ink-muted">{provenance(result)}</p>
      </div>

      <div className="mt-4 divide-y divide-rule border-y border-rule">
        {rows.map(({ key, label }) => {
          const field = result.fields[key];
          const corrected = isReviewField(key) && isCorrected(result, key);
          const value = isReviewField(key) ? effectiveValue(result, key) : field?.value;
          return (
            <FieldRow
              key={key}
              label={label}
              value={isReviewField(key) ? formatValue(effectiveValue(result, key)) : formatField(key, result)}
              empty={isEmptyValue(value)}
              aiValue={corrected ? formatValue((field?.value as string | string[] | null) ?? null) : undefined}
              confidence={field?.confidence ?? 0}
              evidence={field?.evidence ?? []}
              rejected={rejected.filter((r) => (ROW_OF[r.field] ?? r.field) === key)}
              provenance={isReviewField(key) ? provenance(result, key) : "KI-Vorschlag"}
            />
          );
        })}
      </div>

      <Begruendung result={result} review={review} />

      {rejected.length > 0 && (
        <details className="group mt-3">
          <summary className="cursor-pointer text-small text-ink-muted hover:text-ink-strong">
            Verworfene Hypothesen ({rejected.length})
          </summary>
          <ul className="mt-2 space-y-1.5">
            {rejected.map((r, i) => (
              <li key={i} className="grid grid-cols-[112px_1fr] gap-3 text-small">
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

/** sz.ch .box: paper-2 with a 4px left border; cert-check when the photo needs review. */
function Begruendung({ result, review }: { result: AnalysisResult; review: boolean }) {
  const sure = !review && result.overall_confidence >= SURE;
  return (
    <div className={`mt-4 border-l-4 bg-paper-2 px-4 py-3 ${sure ? "border-ink-muted" : "border-cert-check"}`}>
      <p className="text-body">
        Modell-Sicherheit gesamt <span className="font-mono">{formatPct(result.overall_confidence)}</span>
        {" · "}
        {sure ? <span>sicher</span> : <span className="text-warn">Prüfung nötig</span>}
        {result.usage?.budget_hit && <span className="text-warn"> · Budget erreicht</span>}
      </p>
      {result.confidence_explanation && (
        <p className="mt-1 text-small">
          <span className="text-ink-muted">Begründung: </span>
          {result.confidence_explanation}
        </p>
      )}
    </div>
  );
}
