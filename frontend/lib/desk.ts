// Arbeitsplatz logic (FRONTPAGE_PLAN 4): certainty classes, counters, sorting, filtering, search.
import { isEmptyValue } from "./format";
import { REVIEW_FIELDS, SURE, effectiveValue, formatValue } from "./review";
import { needsReview, type AnalysisResult, type PhotoRecord } from "./types";

export interface DeskItem {
  record: PhotoRecord;
  /** null = no result yet. */
  result: AnalysisResult | null;
}

/**
 * The model's verdict, independent of the review (the review has its own counter):
 * "open" = Ortschaft and Gemeinde both not determined, or no result yet;
 * "sure" = overall >= 0.9 and not flagged; "check" = everything else ("Prüfung nötig").
 * Exactly one class per photo, so the three counters add up to the list.
 */
export type ModelClass = "sure" | "check" | "open";

export function modelClass(result: AnalysisResult | null): ModelClass {
  if (!result) return "open";
  if (isEmptyValue(result.fields.locality?.value) && isEmptyValue(result.fields.municipality?.value)) return "open";
  return result.overall_confidence >= SURE && !needsReview(result) ? "sure" : "check";
}

export function isReviewed(result: AnalysisResult | null): boolean {
  return result?.review?.status === "bestaetigt" || result?.review?.status === "korrigiert";
}

export interface Counts {
  total: number;
  sure: number;
  check: number;
  open: number;
  withoutResult: number;
  reviewed: number;
  confirmed: number;
  corrected: number;
}

export function countItems(items: DeskItem[]): Counts {
  const c: Counts = { total: items.length, sure: 0, check: 0, open: 0, withoutResult: 0, reviewed: 0, confirmed: 0, corrected: 0 };
  for (const { result } of items) {
    c[modelClass(result)]++;
    if (!result) c.withoutResult++;
    if (result?.review?.status === "bestaetigt") c.confirmed++;
    if (result?.review?.status === "korrigiert") c.corrected++;
  }
  c.reviewed = c.confirmed + c.corrected;
  return c;
}

export type SortKey = "unsure" | "sure" | "signature" | "series";

export const SORTS: { key: SortKey; label: string }[] = [
  { key: "unsure", label: "Unsicherste zuerst" },
  { key: "sure", label: "Sicherste zuerst" },
  { key: "signature", label: "Nach Signatur" },
  { key: "series", label: "Nach Serie" },
];

export type FilterKey = "all" | ModelClass | "unreviewed" | "reviewed" | "noplace";

export const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Alle" },
  { key: "sure", label: "sicher" },
  { key: "check", label: "Prüfung nötig" },
  { key: "open", label: "nicht bestimmbar" },
  { key: "unreviewed", label: "ungeprüft" },
  { key: "reviewed", label: "geprüft" },
  { key: "noplace", label: "ohne Ort auf der Karte" },
];

/** "SG.CIV.17.40" before "SG.CIV.17.400": compare the dotted parts as numbers where they are numbers. */
export function compareSignature(a: string, b: string): number {
  return a.localeCompare(b, "de-CH", { numeric: true });
}

function sig(item: DeskItem): string {
  return item.record.signature ?? item.record.id;
}

/** A session's key: its first member in signature order, so siblings sort together. */
function seriesKey(item: DeskItem): string {
  const members = [item.record.id, ...(item.record.raw?.session ?? [])].map((id) => id.replace(/^challenge:/, ""));
  return members.sort(compareSignature)[0];
}

export function sortItems(items: DeskItem[], key: SortKey): DeskItem[] {
  const conf = (i: DeskItem) => i.result?.overall_confidence ?? -1; // no result = least sure
  const bySig = (a: DeskItem, b: DeskItem) => compareSignature(sig(a), sig(b));
  const out = [...items];
  switch (key) {
    case "unsure":
      return out.sort((a, b) => conf(a) - conf(b) || bySig(a, b));
    case "sure":
      return out.sort((a, b) => conf(b) - conf(a) || bySig(a, b));
    case "signature":
      return out.sort(bySig);
    case "series":
      return out.sort((a, b) => compareSignature(seriesKey(a), seriesKey(b)) || bySig(a, b));
  }
}

export function filterItems(items: DeskItem[], key: FilterKey): DeskItem[] {
  switch (key) {
    case "all":
      return items;
    case "reviewed":
      return items.filter((i) => isReviewed(i.result));
    case "unreviewed":
      return items.filter((i) => !isReviewed(i.result));
    case "noplace":
      return items.filter((i) => !i.result?.fields.coordinates?.value);
    default:
      return items.filter((i) => modelClass(i.result) === key);
  }
}

/** Search over signature and the values that count (review wins), accent-insensitive. */
export function searchItems(items: DeskItem[], q: string): DeskItem[] {
  const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const needle = norm(q.trim());
  if (!needle) return items;
  return items.filter(({ record, result }) => {
    const values = result ? REVIEW_FIELDS.map((k) => formatValue(effectiveValue(result, k))) : [];
    return norm([record.signature ?? "", record.id, record.title ?? "", ...values].join(" ")).includes(needle);
  });
}

/** "Aufnahmen 2003 bis 2013" from the EXIF dates. */
export function yearSpan(records: PhotoRecord[]): string | null {
  const years = records.map((r) => r.date?.year_from).filter((y): y is number => typeof y === "number");
  if (!years.length) return null;
  const lo = Math.min(...years);
  const hi = Math.max(...years);
  return lo === hi ? `Aufnahmen ${lo}` : `Aufnahmen ${lo} bis ${hi}`;
}

/** Marker class on the map and in the list: reviewed first, then the model class. */
export type CertClass = "confirmed" | ModelClass;

export function certClass(result: AnalysisResult | null): CertClass {
  return isReviewed(result) ? "confirmed" : modelClass(result);
}

/** Worst first: a place shows the least certain of its photos. */
const CLASS_RANK: Record<CertClass, number> = { open: 0, check: 1, sure: 2, confirmed: 3 };

/** One map feature per place (plan 4: no clustering, stacked points would only hit the top one). */
export interface Place {
  /** Integer feature id (MapLibre feature-state needs integers). */
  id: number;
  lat: number;
  lon: number;
  /** Uncertainty radius in metres, the largest of the photos at this spot (0 when unknown). */
  radius_m: number;
  count: number;
  worst: CertClass;
  ids: string[];
}

/** Photos grouped by coordinates rounded to 5 decimals; photos without coordinates are not drawn. */
export function aggregatePlaces(items: DeskItem[]): { places: Place[]; placeOf: Map<string, number>; withoutPlace: number } {
  const byKey = new Map<string, Place>();
  const placeOf = new Map<string, number>();
  let withoutPlace = 0;
  for (const item of items) {
    const c = item.result?.fields.coordinates?.value;
    if (!c) {
      withoutPlace++;
      continue;
    }
    const lat = Number(c.lat.toFixed(5));
    const lon = Number(c.lon.toFixed(5));
    const key = `${lat},${lon}`;
    let place = byKey.get(key);
    if (!place) {
      place = { id: byKey.size + 1, lat, lon, radius_m: 0, count: 0, worst: "confirmed", ids: [] };
      byKey.set(key, place);
    }
    place.radius_m = Math.max(place.radius_m, c.radius_m || 0);
    const cls = certClass(item.result);
    if (CLASS_RANK[cls] < CLASS_RANK[place.worst]) place.worst = cls;
    place.count++;
    place.ids.push(item.record.id);
    placeOf.set(item.record.id, place.id);
  }
  return { places: [...byKey.values()], placeOf, withoutPlace };
}
