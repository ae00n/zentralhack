// The reasoning of a result, placed on the map (Said, 24.10.): the mountains and waters it names, and the
// nearby buildings it compared from above and dropped. Only what lies plausibly around the found spot is
// shown; far matches of a name are left out. Coordinates come from the swisstopo SearchServer (open, CORS),
// so the backend needs no change. Offline or on failure the list is just shorter.
import type { AnalysisResult, PhotoMark } from "@/lib/types";

export type LandmarkKind = "mountain" | "water" | "place";

export interface Landmark {
  name: string;
  kind: LandmarkKind;
  lat: number;
  lon: number;
}

export interface Reasoning {
  spot: { lat: number; lon: number };
  landmarks: Landmark[];
  /** Buildings the agent compared from above near the spot and did not choose. */
  alternatives: { name: string; lat: number; lon: number }[];
  /** True when the result names a building: then the alternatives were dropped, else only checked. */
  chose: boolean;
  /** For the pin's sign: the building and street of the result. */
  building: string | null;
  street: string | null;
}

const SEARCH = "https://api3.geo.admin.ch/rest/services/api/SearchServer";
const LIMIT_KM: Record<LandmarkKind, number> = { mountain: 40, water: 30, place: 40 };
const FAR_WATER_KM = 6; // a lake's centre farther than this: put its sign on the water next to the spot
const NEAR_WATER_KM = 1.2;
const ALTERNATIVE_KM = 2;
const MAX_LANDMARKS = 5;
const TIMEOUT_MS = 1500;

const cache = new Map<string, Promise<{ label: string; lat: number; lon: number }[]>>();

export function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const k = Math.PI / 180;
  const x = (b.lon - a.lon) * k * Math.cos(((a.lat + b.lat) / 2) * k);
  return 6371 * Math.hypot(x, (b.lat - a.lat) * k);
}

function kindOf(label: string): LandmarkKind {
  if (/^(Alpiner Gipfel|Hauptgipfel|Gipfel|Berg|Huegel|Hügel|Felskopf)/i.test(label)) return "mountain";
  if (/^(See|Seeteil|Fluss|Bach|Weiher|Stausee)/i.test(label)) return "water";
  return "place";
}

/** The kind a name suggests by itself ("...stock", "...see"), for hits that are a hut or a camp site. */
export function kindOfName(name: string): LandmarkKind {
  if (/(see|seeli|bach|fluss|muota|reuss|sihl|\baa\b|weiher)$/i.test(name) || /see\b/i.test(name)) return "water";
  if (/(stock|horn|berg|flue|fluh|spitz|gipfel|egg|grat|kopf|mythen|rigi|stuckli|chulm|kulm)/i.test(name)) return "mountain";
  return "place";
}

const RANK: Record<LandmarkKind, number> = { mountain: 0, water: 0, place: 1 };

/** Search variants: as written, then a compound split ("Urirotstock" is "Uri Rotstock" at swisstopo). */
function variants(name: string): string[] {
  const split = name.replace(/^(Uri|Gross|Grosser|Klein|Kleiner|Hoch|Ober|Unter|Vorder|Hinter)(?=[a-zäöü]{3})/i, "$1 ");
  return split !== name ? [name, split] : [name];
}

function lookup(name: string): Promise<{ label: string; lat: number; lon: number }[]> {
  const hit = cache.get(name);
  if (hit) return hit;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  const url = `${SEARCH}?${new URLSearchParams({ searchText: name, type: "locations", sr: "4326", limit: "10" })}`;
  const p = fetch(url, { signal: ctrl.signal })
    .then((r) => (r.ok ? r.json() : { results: [] }))
    .then((j: { results?: { attrs: { label: string; lat: number; lon: number } }[] }) =>
      (j.results ?? []).map((r) => ({ label: r.attrs.label.replace(/<[^>]+>/g, "").trim(), lat: r.attrs.lat, lon: r.attrs.lon })),
    )
    .catch(() => [])
    .finally(() => clearTimeout(timer));
  cache.set(name, p);
  return p;
}

/** A point d km from a towards b. */
function toward(a: { lat: number; lon: number }, b: { lat: number; lon: number }, d: number) {
  const f = d / Math.max(km(a, b), 1e-6);
  return { lat: a.lat + (b.lat - a.lat) * f, lon: a.lon + (b.lon - a.lon) * f };
}

async function place(name: string, spot: { lat: number; lon: number }): Promise<Landmark | null> {
  for (const q of variants(name)) {
    // Mountains and waters before huts, camp sites and streets of the same name, then the nearest.
    const hits = (await lookup(q))
      .map((h) => ({ ...h, kind: kindOf(h.label), d: km(spot, h) }))
      .filter((h) => h.d <= LIMIT_KM[h.kind])
      .sort((a, b) => RANK[a.kind] - RANK[b.kind] || a.d - b.d);
    const h = hits[0];
    if (!h) continue;
    const kind = h.kind === "place" ? kindOfName(name) : h.kind;
    const at = kind === "water" && h.d > FAR_WATER_KM ? toward(spot, h, NEAR_WATER_KM) : h;
    return { name, kind, lat: at.lat, lon: at.lon };
  }
  return null;
}

/** "Marina Fallenbach" and "Marina Fallenbach Brunnen" are the same building. */
function sameName(a: string, b: string): boolean {
  const x = a.toLowerCase().replace(/[()]/g, "");
  const y = b.toLowerCase().replace(/[()]/g, "");
  return x.includes(y) || y.includes(x);
}

/**
 * Marks for the photo itself: the backend's photo_marks when present, else the landmarks the agent placed
 * by hand in a viewpoint_search step (horizontal position only).
 */
export function photoMarksOf(result: AnalysisResult | null): PhotoMark[] {
  if (!result) return [];
  if (result.photo_marks?.length) return result.photo_marks.filter((m) => m.x >= 0 && m.x <= 1);
  const features = new Set(list(result.fields.landscape_features?.value).map((n) => n.toLowerCase()));
  const out: PhotoMark[] = [];
  for (const t of result.trace ?? []) {
    if (t.type !== "tool_call" || t.tool !== "viewpoint_search") continue;
    for (const l of ((t.input?.landmarks as { name?: string; x?: number }[] | undefined) ?? [])) {
      if (!l.name || typeof l.x !== "number" || l.x < 0 || l.x > 1) continue;
      if (features.size && !features.has(l.name.toLowerCase())) continue; // only what the result names
      if (out.some((m) => m.name === l.name)) continue;
      out.push({ name: l.name, kind: kindOfName(l.name) === "water" ? "water" : "mountain", x: l.x, y: null });
    }
  }
  return out;
}

const list = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

export async function reasoningOf(result: AnalysisResult | null): Promise<Reasoning | null> {
  const c = result?.fields.coordinates?.value;
  if (!result || !c) return null;
  const spot = { lat: c.lat, lon: c.lon };
  const f = result.fields;
  const names = (f.landscape_features?.confidence ?? 0) > 0 ? list(f.landscape_features?.value).slice(0, MAX_LANDMARKS) : [];
  const landmarks = (await Promise.all(names.map((n) => place(n, spot)))).filter((l): l is Landmark => l !== null);

  const buildings = list(f.buildings?.value);

  const alternatives: Reasoning["alternatives"] = [];
  for (const t of result.trace ?? []) {
    if (t.type !== "tool_call" || t.tool !== "aerial_view") continue;
    for (const cand of ((t.input?.candidates as { name?: string; lat?: number; lon?: number }[] | undefined) ?? [])) {
      if (typeof cand.lat !== "number" || typeof cand.lon !== "number" || !cand.name) continue;
      if (buildings.some((b) => sameName(b, cand.name!)) || km(spot, { lat: cand.lat, lon: cand.lon }) > ALTERNATIVE_KM) continue;
      if (km(spot, { lat: cand.lat, lon: cand.lon }) < 0.05) continue; // the found spot itself
      if (alternatives.some((a) => a.name === cand.name)) continue;
      alternatives.push({ name: cand.name, lat: cand.lat, lon: cand.lon });
    }
  }
  const street = typeof f.street?.value === "string" ? f.street.value : null;
  return { spot, landmarks, alternatives: alternatives.slice(0, 3), chose: buildings.length > 0, building: buildings[0] ?? null, street };
}
