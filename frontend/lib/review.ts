// Review state of a result (FRONTPAGE_PLAN 3 + 5): which value counts, and where it came from.
// AI values and archivist decisions stay apart in the UI (provenance meta line).
import { NOT_DETERMINED, isEmptyValue } from "./format";
import type { AnalysisResult, ReviewField } from "./types";

/** The five fields the archivist reviews, in the brief's order. */
export const REVIEW_FIELDS: ReviewField[] = ["locality", "municipality", "buildings", "landscape_features", "street"];

/** Ralph's acceptance line: at or above this a value counts as "sicher". */
export const SURE = 0.9;

type FieldValue = string | string[] | null;

export function aiValue(result: AnalysisResult, key: ReviewField): FieldValue {
  return (result.fields[key]?.value as FieldValue | undefined) ?? null;
}

/** True when the archivist corrected this field. */
export function isCorrected(result: AnalysisResult, key: ReviewField): boolean {
  const r = result.review;
  return r?.status === "korrigiert" && Object.prototype.hasOwnProperty.call(r.fields ?? {}, key);
}

/** The value that counts: the archivist's correction, else the AI value. */
export function effectiveValue(result: AnalysisResult, key: ReviewField): FieldValue {
  return isCorrected(result, key) ? ((result.review!.fields[key] as FieldValue) ?? null) : aiValue(result, key);
}

export function formatValue(value: FieldValue): string {
  if (isEmptyValue(value)) return NOT_DETERMINED;
  return Array.isArray(value) ? value.join("; ") : String(value);
}

/** "24.10.2026 14:02" */
function stamp(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("de-CH", { day: "2-digit", month: "2-digit", year: "numeric" });
  const time = d.toLocaleTimeString("de-CH", { hour: "2-digit", minute: "2-digit" });
  return `${date} ${time}`;
}

/**
 * Provenance meta line for a field (or the whole result when key is omitted):
 * "KI-Vorschlag · ungeprüft", "geprüft · bestätigt 24.10.2026 14:02", "korrigiert · KI: Brunnen".
 */
export function provenance(result: AnalysisResult, key?: ReviewField): string {
  const r = result.review;
  if (!r || r.status === "offen") return "KI-Vorschlag · ungeprüft";
  if (key && isCorrected(result, key)) return `korrigiert · KI: ${formatValue(aiValue(result, key))}`;
  return `geprüft · bestätigt ${stamp(r.reviewed_at)}`.trim();
}

/** Suggested archive title "Objekt, Ort" (Staatsarchiv pattern, plan section 3), or null. */
export function suggestedTitle(result: AnalysisResult): string | null {
  const buildings = effectiveValue(result, "buildings");
  const locality = effectiveValue(result, "locality") ?? effectiveValue(result, "municipality");
  const object = Array.isArray(buildings) ? buildings[0] : buildings;
  const place = Array.isArray(locality) ? locality[0] : locality;
  if (object && place) return `${object}, ${place}`;
  return object || place || null;
}
