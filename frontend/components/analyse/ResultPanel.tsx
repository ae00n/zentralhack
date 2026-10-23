// Erschliessung (FRONTPAGE_PLAN 5): suggested title, the brief's five fields in fixed order with
// "nicht bestimmbar", per-field Modell-Sicherheit and provenance, then the Begründung box.
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

/** Korrigieren in place (plan 5, review rule 3): one input per brief field, prefilled with the value that counts. */
export interface EditState {
  drafts: Record<ReviewField, string>;
  /** Field that gets focus and selection. */
  focus: ReviewField;
  onChange: (key: ReviewField, value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  /** Ortschaft / Gemeinde suggestions: the 30 Gemeinden. */
  gemeinden: string[];
}

const GEMEINDE_FIELDS: ReviewField[] = ["locality", "municipality"];

function Editor({ k, edit }: { k: ReviewField; edit: EditState }) {
  return (
    <input
      value={edit.drafts[k]}
      onChange={(e) => edit.onChange(k, e.target.value)}
      onKeyDown={(e) => {
        if (e.nativeEvent.isComposing) return;
        if (e.key === "Enter") {
          e.preventDefault();
          edit.onSave();
        } else if (e.key === "Escape") {
          e.preventDefault();
          edit.onCancel();
        }
      }}
      ref={(el) => {
        if (el && k === edit.focus && document.activeElement !== el && !el.dataset.focused) {
          el.dataset.focused = "1";
          el.focus();
          el.select();
        }
      }}
      list={GEMEINDE_FIELDS.includes(k) ? "gemeinden-list" : undefined}
      placeholder="nicht bestimmbar"
      autoComplete="off"
      // Same width in every row: the value column of the field grid (polish 4, field input recipe).
      className="h-8 w-full rounded border border-rule/[0.12] bg-paper px-2 text-base text-ink outline-none transition-colors duration-hover placeholder:text-ink-muted hover:border-rule/20 focus-visible:ring-2 focus-visible:ring-focus/50"
    />
  );
}

export default function ResultPanel({ result, edit }: { result: AnalysisResult; edit?: EditState | null }) {
  const review = needsReview(result);
  const rejected = result.rejected_hypotheses ?? [];
  const title = suggestedTitle(result);
  // The five brief fields always show (empty ones as "nicht bestimmbar"); postcard extras only when present.
  const rows = FIELD_ROWS.filter(({ key }) => isReviewField(key) || result.fields[key]);

  return (
    <section className="fade-in">
      <div className="flex items-baseline justify-between gap-3">
        <h2
          id="erschliessung-heading"
          tabIndex={-1}
          className="rounded-sm text-meta font-medium uppercase tracking-[0.06em] text-ink-muted"
        >
          Erschliessung
        </h2>
        <p className="text-meta text-ink-muted">{provenance(result)}</p>
      </div>

      {/* Suggested title in the archive pattern "Objekt, Ort" (Titel). */}
      <p className="mt-1 text-h1 text-ink" title="Titel (Vorschlag)">
        {title ?? <span className="text-ink-muted">nicht bestimmbar</span>}
      </p>

      <div className="mt-3 border-t border-rule/[0.06]">
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
              fieldKey={isReviewField(key) ? key : undefined}
              editor={edit && isReviewField(key) ? <Editor k={key} edit={edit} /> : undefined}
            />
          );
        })}
      </div>

      {edit && (
        <datalist id="gemeinden-list">
          {edit.gemeinden.map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
      )}

      <Begruendung result={result} review={review} />

      {rejected.length > 0 && (
        <details className="group mt-3">
          <summary className="cursor-pointer list-none text-meta text-ink-muted hover:text-ink">
            Verworfene Hypothesen ({rejected.length})
          </summary>
          <ul className="mt-2 space-y-1.5">
            {rejected.map((r, i) => (
              <li key={i} className="grid grid-cols-[88px_1fr] gap-3 text-ui sm:grid-cols-[112px_1fr]">
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

    </section>
  );
}

/** Begründung box (polish 4): soft paper-2, 2 px left border in cert-check, or cert-sure when sicher. */
function Begruendung({ result, review }: { result: AnalysisResult; review: boolean }) {
  const sure = !review && result.overall_confidence >= SURE;
  return (
    <div className={`mt-4 rounded border-l-2 bg-paper-2/70 px-3 py-2.5 text-base ${sure ? "border-cert-sure" : "border-cert-check"}`}>
      <p>
        Modell-Sicherheit gesamt <span className="tnum font-medium">{formatPct(result.overall_confidence)}</span>
        {" · "}
        {sure ? <span>sicher</span> : <span className="text-warn">Prüfung nötig</span>}
        {result.usage?.budget_hit && <span className="text-warn"> · Budget erreicht</span>}
      </p>
      {result.confidence_explanation && (
        <p className="mt-1">
          <span className="text-ink-muted">Begründung: </span>
          {result.confidence_explanation}
        </p>
      )}
    </div>
  );
}
