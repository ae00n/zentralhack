// Display helpers shared by views. UI strings are German.
import type { AnalysisResult, Coordinates, FieldKey, PhotoRecord } from "./types";

export function isUndated(r: PhotoRecord): boolean {
  return !r.date || (r.date.year_from === null && r.date.year_to === null);
}

/** Muted meta line, facts joined by " · ": "SG.CIV.12.4743 · Entstehung: keine Angabe". */
export function metaLine(r: PhotoRecord): string {
  const entstehung = r.date?.raw?.trim() || "keine Angabe";
  return [r.signature ?? r.id, `Entstehung: ${entstehung}`].join(" · ");
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
  if (value === null || value === undefined) return "unbekannt";
  switch (key) {
    case "buildings":
    case "landscape_features":
      return (value as string[]).length ? (value as string[]).join(", ") : "keine erkannt";
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

/** Rejected hypothesis values can be any JSON value. */
export function formatAny(value: unknown): string {
  if (value === null || value === undefined) return "unbekannt";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Share 0..1 as "71 %" (narrow no-break space, Swiss style); null as "–". */
export function formatPct(x: number | null | undefined): string {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)} %`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-CH");
}
