// Display helpers shared by views. UI strings are German.
import type { AnalysisResult, Coordinates, FieldKey, PhotoRecord } from "./types";

export function isUndated(r: PhotoRecord): boolean {
  return !r.date || (r.date.year_from === null && r.date.year_to === null);
}

/** Text for a field the agent could not prove (the brief's term). */
export const NOT_DETERMINED = "nicht bestimmbar";

/**
 * Muted meta line, facts joined by " · ". Challenge photos: "SG.CIV.17.3 · Aufnahmedatum 24.02.2005"
 * (EXIF date); archive cards: "SG.CIV.12.4743 · Entstehung: keine Angabe".
 */
export function metaLine(r: PhotoRecord): string {
  const date = r.date?.raw?.trim() || "keine Angabe";
  const when = r.source === "challenge" ? `Aufnahmedatum ${date}` : `Entstehung: ${date}`;
  return [r.signature ?? r.id, when].join(" · ");
}

export function photoTitle(r: PhotoRecord): string {
  return r.title?.trim() || "Ohne Titel";
}

/** Route to the analysis screen; ids contain ":" and "#". */
export function analyseHref(id: string): string {
  return `/analyse/${encodeURIComponent(id)}`;
}

export function formatCoordinates(c: Coordinates): string {
  return `${c.lat.toFixed(4)}, ${c.lon.toFixed(4)} · ±${Math.round(c.radius_m)} m`;
}

/** Display value of a result row. The Jahrzehnt row also carries year_range (question 2.4). */
export function formatField(key: FieldKey, result: AnalysisResult): string {
  const value = result.fields[key]?.value;
  if (isEmptyValue(value)) return NOT_DETERMINED;
  switch (key) {
    case "buildings":
    case "landscape_features":
      return (value as string[]).join("; ");
    case "decade": {
      const range = result.fields.year_range?.value;
      return range ? `${value}er · ${range.from} bis ${range.to}` : `${value}er`;
    }
    case "coordinates":
      return formatCoordinates(value as Coordinates);
    default:
      return String(value);
  }
}

/** v3: a field that cannot be determined has value null (or an empty list). */
export function isEmptyValue(value: unknown): boolean {
  return value === null || value === undefined || (Array.isArray(value) && value.length === 0) || value === "";
}

/** Rejected hypothesis values can be any JSON value. */
export function formatAny(value: unknown): string {
  if (value === null || value === undefined) return NOT_DETERMINED;
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Share 0..1 as "71 %" (narrow no-break space, Swiss style); null as "nicht bestimmbar". */
export function formatPct(x: number | null | undefined): string {
  return x === null || x === undefined ? NOT_DETERMINED : `${Math.round(x * 100)} %`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-CH");
}
