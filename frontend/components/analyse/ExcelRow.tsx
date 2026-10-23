"use client";

// Excel-Zeile (live), FRONTPAGE_PLAN 5: the row as the export will write it, computed client-side from
// result + review, so a correction changes it at once. Rules follow Said's agent/server/export.py:
// review values win, lists joined "; ", empty stays empty, Pruefung_noetig "nein" once reviewed.
import { useEffect, useRef } from "react";
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

export default function ExcelRow({ record, result }: { record: PhotoRecord; result: AnalysisResult }) {
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
      <h2 className="text-h3">Excel-Zeile</h2>
      <p className="text-meta text-ink-muted">So schreibt der Export diese Zeile.</p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full border-collapse text-ui">
          <thead>
            <tr>
              {row.map(([k]) => (
                <th key={k} className="whitespace-nowrap border border-rule/[0.12] bg-paper-2 px-2 py-1 text-left font-mono text-meta font-normal text-ink-muted">
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {row.map(([k, v]) => (
                <td
                  // A new key restarts the flash animation for a changed cell.
                  key={changed.has(k) ? `${k}:${v}` : k}
                  className={`border border-rule/[0.12] px-2 py-1 align-top ${changed.has(k) ? "cell-flash" : ""}`}
                >
                  {v}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
