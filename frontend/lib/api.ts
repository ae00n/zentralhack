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
import { MOCK_RESULT_VARIANTS } from "@/mocks/results";

export type Mode = "mock" | "live" | "demo";

export const MODE: Mode = parseMode(process.env.NEXT_PUBLIC_MODE);
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const FIXTURES = "/fixtures";
const SWISSTOPO_WMTS = "https://wmts.geo.admin.ch";

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

export class ApiError extends Error {
  constructor(
    public status: number,
    public path: string,
  ) {
    super(`HTTP ${status} on ${path}`);
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, url);
  return (await res.json()) as T;
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

export async function getEvalSummary(): Promise<EvalSummary | null> {
  if (MODE === "mock") return fixture<EvalSummary>("eval_summary.json");
  try {
    return await backend<EvalSummary>("/eval/summary");
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

/** Download link for the export. Mock mode only has a CSV fixture. */
export function exportUrl(format: "csv" | "json", ids?: string[]): string {
  if (MODE === "mock") return `${FIXTURES}/export.csv`;
  return `${API_URL}/export.${format}${query({ ids: ids?.join(",") })}`;
}

// --- trace replay (mock + demo mode; live mode streams SSE, build step 8) ---

/**
 * Plays trace items back one by one so a cached result looks live.
 * Returns a cancel function. Delay per step follows the recorded ms, clamped to a calm pace.
 */
export function replayTrace(
  trace: TraceItem[],
  onStep: (item: TraceItem) => void,
  onDone?: () => void,
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let i = 0;

  const next = () => {
    if (cancelled) return;
    if (i >= trace.length) {
      onDone?.();
      return;
    }
    const item = trace[i++];
    onStep(item);
    timer = setTimeout(next, Math.min(1500, Math.max(600, item.ms)));
  };
  timer = setTimeout(next, 300);

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}
