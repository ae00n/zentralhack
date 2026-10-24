"use client";

// Excel-Zeile (live), FRONTPAGE_PLAN 5: the row as the export will write it, computed client-side from
// result + review, so a correction changes it at once. Rules follow Said's agent/server/export.py:
// review values win, lists joined "; ", empty stays empty, Pruefung_noetig "nein" once reviewed.
import { Fragment, useEffect, useRef } from "react";
import { isEmptyValue } from "@/lib/format";
import { REVIEW_FIELDS, SURE, effectiveValue } from "@/lib/review";
import { needsReview, type AnalysisResult, type PhotoRecord } from "@/lib/types";

const COLUMNS: Record<(typeof REVIEW_FIELDS)[number], string> = {
  locality: "Ortschaft",
  municipality: "Gemeinde",
  buildings: "Gebaeude",
  landscape_features: "See_Fluss_Berg",
  street: "Strasse",
};

/** Said's _needs_review: the flag, below 0.9, or Ortschaft / Gemeinde unknown (AI values). */
function flagged(result: AnalysisResult): boolean {
  const unknown = (["locality", "municipality"] as const).some((k) => isEmptyValue(result.fields[k]?.value));
  return needsReview(result) || result.overall_confidence < SURE || unknown;
}

function cells(record: PhotoRecord, result: AnalysisResult): [string, string][] {
  const status = result.review?.status;
  const reviewed = status === "bestaetigt" || status === "korrigiert";
  const fileName =
    record.source === "challenge" && record.raw?.file_name ? record.raw.file_name : `${record.source_id}.jpg`;
  const values = REVIEW_FIELDS.map((k): [string, string] => {
    const v = effectiveValue(result, k);
    return [COLUMNS[k], v === null ? "" : Array.isArray(v) ? v.join("; ") : v];
  });
  return [
    ["Dateiname", fileName],
    ...values,
    ["Konfidenz_Gesamt", result.overall_confidence.toFixed(2)],
    ["Pruefung_noetig", reviewed || !flagged(result) ? "nein" : "ja"],
    ["Review_Status", status ?? "offen"],
  ];
}

/** `heading={false}` when a collapsible section around it already says "Excel-Zeile" (detail inspector). */
export default function ExcelRow({ record, result, heading = true }: { record: PhotoRecord; result: AnalysisResult; heading?: boolean }) {
  const row = cells(record, result);
  // Cells that changed since the last committed render flash (400 ms fade from paper-2). The ref is
  // updated after commit, so a double render (dev StrictMode) still sees the old values.
  const prev = useRef<Map<string, string>>(new Map());
  const changed = new Set(row.filter(([k, v]) => prev.current.has(k) && prev.current.get(k) !== v).map(([k]) => k));
  useEffect(() => {
    prev.current = new Map(row);
  });

  return (
    <div>
      {heading && <h2 className="text-h3">Excel-Zeile</h2>}
      <p className="text-meta text-ink-muted">So schreibt der Export diese Zeile.</p>
      {/* Key / value list (polish 6): every column visible, no horizontal scroll. */}
      <dl className="mt-2 grid grid-cols-[136px_minmax(0,1fr)] gap-x-3 font-mono text-meta">
        {row.map(([k, v]) => (
          // A new key restarts the flash animation for a changed cell.
          <Fragment key={changed.has(k) ? `${k}:${v}` : k}>
            <dt className="border-b border-rule/[0.06] py-1 text-ink-muted">{k}</dt>
            <dd className={`break-words border-b border-rule/[0.06] px-1 py-1 text-ink ${changed.has(k) ? "cell-flash" : ""}`}>{v}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  );
}
