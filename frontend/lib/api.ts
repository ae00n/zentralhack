// The only place that talks to the backend. Components never call fetch directly.
// NEXT_PUBLIC_MODE: mock = fixtures from public/fixtures, live = real backend + /analyze,
// demo = real backend, results replayed from the cache (no analysis is ever triggered).
import type {
  AnalysisResult,
  DemoItem,
  EvalSummary,
  Health,
  PhotoList,
  PhotoRecord,
  Timeline,
  TraceItem,
} from "./types";
import { MOCK_DEMO_IDS, MOCK_PHOTOS } from "@/mocks/photos";
import { mockEvalExtras } from "@/mocks/eval";
import { MOCK_RESULT_VARIANTS } from "@/mocks/results";

export type Mode = "mock" | "live" | "demo";

export const MODE: Mode = parseMode(process.env.NEXT_PUBLIC_MODE);
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const FIXTURES = "/fixtures";
// Same value as the backend's /health tiles_url when online.
const SWISSTOPO_WMTS = "https://wmts.geo.admin.ch/1.0.0";

function parseMode(v: string | undefined): Mode {
  return v === "live" || v === "demo" ? v : "mock";
}

/** IDs contain ":" and crops "#" (stasz:514200#1); "#" would otherwise be cut off as a URL fragment. */
function enc(id: string): string {
  return encodeURIComponent(id);
}

/** Backend URLs like image_url and tiles_url may be relative ("/images/..."). */
export function absolute(url: string): string {
  return /^https?:\/\//.test(url) ? url : `${API_URL}${url.startsWith("/") ? "" : "/"}${url}`;
}

/** status 0 = no response at all (backend down, Wi-Fi off without a local backend). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public path: string,
  ) {
    super(status === 0 ? `no response from ${path}` : `HTTP ${status} on ${path}`);
  }
}

async function getJson<T>(url: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store" });
  } catch {
    throw new ApiError(0, url);
  }
  if (!res.ok) throw new ApiError(res.status, url);
  return (await res.json()) as T;
}

/** German text for an error shown in the UI. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    return e.status === 0 ? `Backend nicht erreichbar (${MODE === "mock" ? "Fixtures" : API_URL})` : `Fehler ${e.status}`;
  }
  return e instanceof Error ? e.message : String(e);
}

function backend<T>(path: string): Promise<T> {
  return getJson<T>(`${API_URL}${path}`);
}

function fixture<T>(name: string): Promise<T> {
  return getJson<T>(`${FIXTURES}/${name}`);
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

// --- endpoints (docs/CONTRACTS.md section 5) ---

export async function getHealth(): Promise<Health> {
  if (MODE === "mock") return { ok: true, model: "fixture", offline: false, tiles_url: SWISSTOPO_WMTS };
  return backend<Health>("/health");
}

export interface PhotoQuery {
  split?: string;
  municipality?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

async function mockPhotos(): Promise<PhotoRecord[]> {
  const record = await fixture<PhotoRecord>("photo_record.json");
  return [...MOCK_PHOTOS, record];
}

export async function listPhotos(params: PhotoQuery = {}): Promise<PhotoList> {
  if (MODE === "mock") {
    const { split, municipality, q, limit = 50, offset = 0 } = params;
    const needle = q?.toLowerCase();
    const all = (await mockPhotos()).filter(
      (r) =>
        (!split || r.split === split) &&
        (!municipality || r.municipality === municipality) &&
        (!needle || `${r.title} ${r.signature}`.toLowerCase().includes(needle)),
    );
    return { items: all.slice(offset, offset + limit), total: all.length };
  }
  return backend<PhotoList>(`/photos${query({ limit: 50, offset: 0, ...params })}`);
}

export async function getPhoto(id: string): Promise<PhotoRecord> {
  if (MODE === "mock") {
    const found = (await mockPhotos()).find((r) => r.id === id);
    if (!found) throw new ApiError(404, `/photos/${enc(id)}`);
    return found;
  }
  return backend<PhotoRecord>(`/photos/${enc(id)}`);
}

/** Every image goes through here; in mock mode all ids show the public-domain fixture image. */
export function imageUrl(id: string, width?: number): string {
  if (MODE === "mock") return `${FIXTURES}/sample.jpg`;
  return `${API_URL}/images/${enc(id)}${query({ w: width })}`;
}

/** Cached result, or null when the backend has none (404). */
export async function getResult(photoId: string): Promise<AnalysisResult | null> {
  if (MODE === "mock") {
    const base = await fixture<AnalysisResult>("analysis_result.json");
    const variant = MOCK_RESULT_VARIANTS[photoId];
    return { ...(variant ? variant(base) : base), photo_id: photoId };
  }
  try {
    return await backend<AnalysisResult>(`/results/${enc(photoId)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getTimeline(lat: number, lon: number, radiusM = 1000): Promise<Timeline> {
  if (MODE === "mock") return fixture<Timeline>("timeline.json");
  return backend<Timeline>(`/timeline${query({ lat, lon, radius_m: radiusM })}`);
}

/**
 * Real eval numbers, or null when there are none yet. Said's /eval/summary serves the made-up fixture
 * until the first eval run (marked by _fixture_note); outside mock mode that counts as none (question 3.9).
 */
export async function getEvalSummary(): Promise<EvalSummary | null> {
  if (MODE === "mock") return mockEvalExtras(await fixture<EvalSummary>("eval_summary.json"));
  try {
    const s = await backend<EvalSummary>("/eval/summary");
    return s._fixture_note ? null : s;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function getDemo(): Promise<DemoItem[]> {
  if (MODE === "mock") {
    const all = await mockPhotos();
    return MOCK_DEMO_IDS.flatMap((id) => {
      const record = all.find((r) => r.id === id);
      return record ? [{ id, why: "Beispieldaten", record }] : [];
    });
  }
  return backend<DemoItem[]>("/demo");
}

export type TileLayer = "ch.swisstopo.swissimage" | "ch.swisstopo.zeitreihen";

const TILE_EXT: Record<TileLayer, string> = {
  "ch.swisstopo.swissimage": "jpeg",
  "ch.swisstopo.zeitreihen": "png",
};

/** Base for tileTemplate: /health tiles_url, or swisstopo directly when the backend is not reachable. */
export async function getTilesUrl(): Promise<{ tilesUrl: string; offline: boolean }> {
  try {
    const h = await getHealth();
    return { tilesUrl: h.tiles_url || SWISSTOPO_WMTS, offline: h.offline };
  } catch {
    return { tilesUrl: SWISSTOPO_WMTS, offline: false };
  }
}

/**
 * MapLibre raster template for a layer and TIME ("current" for swissimage, a map_years value for zeitreihen).
 * Online it is the swisstopo WMTS path; offline the backend's /tiles route, which has a different shape (question 3.3).
 */
export function tileTemplate(tilesUrl: string, layer: TileLayer, time: string | number): string {
  const base = absolute(tilesUrl).replace(/\/$/, "");
  const ext = TILE_EXT[layer];
  if (base.startsWith(SWISSTOPO_WMTS)) return `${base}/${layer}/default/${time}/3857/{z}/{x}/{y}.${ext}`;
  return `${base}/${layer}/${time}/{z}/{x}/{y}.${ext}`;
}

// --- export (CONTRACTS section 6) ---

export type ExportFormat = "csv" | "json";

/** One CSV line split on ";", honouring "..." quoting. Enough for the export fixture. */
function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') cell += line[i++];
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ";") {
      out.push(cell);
      cell = "";
    } else cell += c;
  }
  out.push(cell);
  return out;
}

/** Mock JSON: the CSV fixture as rows keyed by the CSV header (question 3.13, same as Said's /export.json). */
function csvToRows(csv: string): Record<string, string>[] {
  const [header, ...lines] = csv.replace(/^﻿/, "").split(/\r?\n/).filter(Boolean);
  const keys = splitCsvLine(header);
  return lines.map((l) => Object.fromEntries(splitCsvLine(l).map((v, i) => [keys[i], v])));
}

async function fetchBlob(url: string): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store" });
  } catch {
    throw new ApiError(0, url);
  }
  if (!res.ok) throw new ApiError(res.status, url);
  return res.blob(); // bytes as sent, so the CSV keeps its BOM (Excel needs it for umlauts)
}

/** "zeitreise-schwyz_stasz-514200.csv", "zeitreise-schwyz_auswahl-3.json", "zeitreise-schwyz_alle.csv". */
function exportFilename(format: ExportFormat, ids?: string[]): string {
  const part = !ids?.length ? "alle" : ids.length === 1 ? ids[0].replace(/[^\w.-]+/g, "-") : `auswahl-${ids.length}`;
  return `zeitreise-schwyz_${part}.${format}`;
}

/**
 * Fetches the export and saves it as a file. Returns the number of rows; 0 means nothing was saved
 * (no analysed photo among the ids). Fetched as a blob so JSON downloads instead of opening in a tab
 * and the file gets a readable name (a cross-origin <a download> ignores the name).
 */
export async function downloadExport(format: ExportFormat, ids?: string[]): Promise<number> {
  let blob: Blob;
  let rows: number;
  if (MODE === "mock") {
    // Only a CSV fixture exists; every selection gets that one row.
    const csv = await fetchBlob(`${FIXTURES}/export.csv`);
    if (format === "csv") {
      blob = csv;
      rows = csvToRows(await csv.text()).length;
    } else {
      const data = csvToRows(await csv.text());
      blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      rows = data.length;
    }
  } else {
    blob = await fetchBlob(`${API_URL}/export.${format}${query({ ids: ids?.join(",") })}`);
    const text = await blob.text();
    rows = format === "json" ? (JSON.parse(text) as unknown[]).length : csvToRows(text).length;
  }
  if (rows === 0) return 0;

  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = exportFilename(format, ids);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
  return rows;
}

// --- trace replay (mock + demo mode; live mode streams SSE, build step 8) ---

// A real trace can have 20+ steps; the pitch cannot wait a minute for it.
const REPLAY_MAX_MS = 15_000;

/** Delay after each step: the recorded ms clamped to a calm pace, scaled down so the whole replay fits REPLAY_MAX_MS. */
function replayDelays(trace: TraceItem[]): number[] {
  const delays = trace.map((t) => Math.min(1500, Math.max(600, t.ms)));
  const total = delays.reduce((a, b) => a + b, 0);
  const scale = total > REPLAY_MAX_MS ? REPLAY_MAX_MS / total : 1;
  return delays.map((d) => Math.max(250, Math.round(d * scale)));
}

/**
 * Plays trace items back one by one so a cached result looks live.
 * Returns a cancel function.
 */
export function replayTrace(
  trace: TraceItem[],
  onStep: (item: TraceItem) => void,
  onDone?: () => void,
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let i = 0;
  const delays = replayDelays(trace);

  const next = () => {
    if (cancelled) return;
    if (i >= trace.length) {
      onDone?.();
      return;
    }
    onStep(trace[i]);
    timer = setTimeout(next, delays[i++]);
  };
  timer = setTimeout(next, 300);

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}
