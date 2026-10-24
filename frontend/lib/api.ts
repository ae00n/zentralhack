// The only place that talks to the backend. Components never call fetch directly.
// NEXT_PUBLIC_MODE: mock = fixtures from public/fixtures, live = real backend + /analyze,
// demo = real backend, results replayed from the cache (no analysis is ever triggered).
import type {
  AnalysisResult,
  Batch,
  DemoItem,
  EvalSummary,
  Evidence,
  FieldKey,
  Health,
  PhotoList,
  PhotoRecord,
  QcSummary,
  Review,
  ReviewStatus,
  Timeline,
  TraceItem,
} from "./types";
import { MOCK_CHALLENGE, MOCK_CHALLENGE_RESULTS } from "@/mocks/challenge";
import { MOCK_QC, mockEvalExtras } from "@/mocks/eval";

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

/** Mock records: the three challenge photos plus the contract fixture record (the archive reference card). */
async function mockPhotos(): Promise<PhotoRecord[]> {
  const record = await fixture<PhotoRecord>("photo_record.json");
  return [...MOCK_CHALLENGE, record];
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
    const upload = mockUploads.get(id);
    if (upload) return upload.record;
    const found = (await mockPhotos()).find((r) => r.id === id);
    if (!found) throw new ApiError(404, `/photos/${enc(id)}`);
    return found;
  }
  return backend<PhotoRecord>(`/photos/${enc(id)}`);
}

/** Every image goes through here; in mock mode all ids show the public-domain fixture image, uploads their own. */
export function imageUrl(id: string, width?: number): string {
  if (MODE === "mock") return mockUploads.get(id)?.url ?? `${FIXTURES}/sample.jpg`;
  return `${API_URL}/images/${enc(id)}${query({ w: width })}`;
}

/** Cached result, or null when the backend has none (404). */
export async function getResult(photoId: string): Promise<AnalysisResult | null> {
  if (MODE === "mock") {
    const upload = mockUploads.get(photoId);
    if (upload && !upload.result) return null; // still running
    const mock = MOCK_CHALLENGE_RESULTS[photoId] ?? upload?.result;
    if (mock) return mockReviews.has(photoId) ? { ...mock, review: mockReviews.get(photoId) } : mock;
    const base = await fixture<AnalysisResult>("analysis_result.json");
    return { ...base, photo_id: photoId };
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

/**
 * The hand-checked QC sample for the Nachweis page, or null while there is none (proposed GET /qc/summary;
 * plan 6: without it the page shows only the postcard eval).
 */
export async function getQcSummary(): Promise<QcSummary | null> {
  if (MODE === "mock") return MOCK_QC;
  try {
    return await backend<QcSummary>("/qc/summary");
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}

export async function getDemo(): Promise<DemoItem[]> {
  if (MODE === "mock") {
    const all = await mockPhotos();
    return all.filter((r) => r.split === "challenge").map((record) => ({ id: record.id, why: "Beispieldaten", record }));
  }
  return backend<DemoItem[]>("/demo");
}

// --- challenge set (CONTRACTS v3, FRONTPAGE_PLAN section 8) ---

/** Mock mode keeps reviews in memory, so Bestätigen / Korrigieren work without a backend. */
const mockReviews = new Map<string, Review>();

/**
 * The SG.CIV.17 photos, in Said's natural signature order. priority 1 = the Prio-1 set of 50.
 * The raw.priority filter also runs client-side, in case a backend ignores ?priority.
 */
export async function listChallenge({ priority }: { priority?: number } = {}): Promise<PhotoRecord[]> {
  const items =
    MODE === "mock"
      ? (await mockPhotos()).filter((r) => r.split === "challenge")
      : (await backend<PhotoList>(`/photos${query({ split: "challenge", priority, limit: 1000 })}`)).items;
  return priority === undefined ? items : items.filter((r) => r.raw?.priority === priority);
}

const resultCache = new Map<string, AnalysisResult | null>();
const FAN_OUT = 6;

/**
 * Results for many photos (desk pins, counters, list meta lines). Tries a bulk GET /results?ids=
 * (asked from Said, FRONTPAGE_PLAN 9); without it, fans out over GET /results/{id}, 6 at a time.
 * Both paths fill an in-memory cache. Photos without a result map to null.
 */
export async function listResults(ids: string[]): Promise<Map<string, AnalysisResult | null>> {
  const missing = ids.filter((id) => !resultCache.has(id));
  if (missing.length && MODE !== "mock") {
    try {
      const bulk = await backend<AnalysisResult[] | { items: AnalysisResult[] }>(`/results${query({ ids: missing.join(",") })}`);
      const list = Array.isArray(bulk) ? bulk : bulk.items;
      for (const r of list) resultCache.set(r.photo_id, r);
      for (const id of missing) if (!resultCache.has(id)) resultCache.set(id, null);
    } catch (e) {
      if (!(e instanceof ApiError) || (e.status !== 404 && e.status !== 405)) throw e;
    }
  }
  const todo = ids.filter((id) => !resultCache.has(id));
  let next = 0;
  const worker = async () => {
    while (next < todo.length) {
      const id = todo[next++];
      resultCache.set(id, await getResult(id));
    }
  };
  await Promise.all(Array.from({ length: Math.min(FAN_OUT, todo.length) }, worker));
  return new Map(ids.map((id) => [id, resultCache.get(id) ?? null]));
}

export interface ReviewBody {
  status: ReviewStatus;
  fields?: Review["fields"];
  note?: string | null;
}

/**
 * POST /review/{id}: Bestätigen / Korrigieren, or "offen" to undo. A second POST overwrites the first
 * (Said's agent/server/app.py). Returns the updated result.
 */
export async function postReview(photoId: string, body: ReviewBody): Promise<AnalysisResult> {
  const review: Review = {
    status: body.status,
    fields: body.fields ?? {},
    note: body.note ?? null,
    reviewed_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  };
  let updated: AnalysisResult;
  if (MODE === "mock") {
    const current = await getResult(photoId);
    if (!current) throw new ApiError(404, `/review/${enc(photoId)}`);
    mockReviews.set(photoId, review);
    updated = { ...current, review };
  } else {
    const url = `${API_URL}/review/${enc(photoId)}`;
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: review.status, fields: review.fields, note: review.note }),
      });
    } catch {
      throw new ApiError(0, url);
    }
    if (!res.ok) throw new ApiError(res.status, url);
    updated = await res.json();
  }
  resultCache.set(photoId, updated);
  return updated;
}

let gemeinden: Promise<string[]> | null = null;

/** The 30 Gemeinden for the Ortschaft / Gemeinde combobox (contracts/fixtures/gemeinden.json, served from
 *  public/fixtures in every mode). */
export function getGemeinden(): Promise<string[]> {
  gemeinden ??= getJson<{ name: string }[]>(`${FIXTURES}/gemeinden.json`)
    .then((g) => g.map((x) => x.name).sort((a, b) => a.localeCompare(b, "de-CH")))
    .catch(() => []);
  return gemeinden;
}

/**
 * The Excel deliverable (sheets Metadaten + Methode). A plain <a download> link: Said sends a
 * Content-Disposition file name. Mock mode has no .xlsx fixture and links the CSV fixture instead.
 */
export function exportXlsxUrl(
  q: { split?: string; priority?: number; ids?: string[]; batch?: string } = { split: "challenge", priority: 1 },
): string {
  if (MODE === "mock") return `${FIXTURES}/export.csv`;
  return `${API_URL}/export.xlsx${query({ split: q.split, priority: q.priority, ids: q.ids?.join(","), batch: q.batch })}`;
}

export interface ReferenceMatch {
  evidence: Evidence;
  field: FieldKey;
  /** true only when Said marks the match LightGlue-verified; otherwise the best-scoring similar image. */
  verified: boolean;
}

/**
 * "Das Archiv kennt diesen Ort": the first similar_image evidence with a ref_id and verified === true;
 * until Said adds `verified`, the one with the highest score. null when there is none.
 */
export function bestReferenceMatch(result: AnalysisResult): ReferenceMatch | null {
  const all = (Object.entries(result.fields) as [FieldKey, AnalysisResult["fields"][FieldKey]][]).flatMap(([field, f]) =>
    (f?.evidence ?? [])
      .filter((e) => e.kind === "similar_image" && e.ref_id && e.supports !== false)
      .map((evidence) => ({ evidence, field })),
  );
  const verified = all.find((m) => m.evidence.verified === true);
  if (verified) return { ...verified, verified: true };
  const best = all.reduce<(typeof all)[number] | null>(
    (b, m) => (!b || (m.evidence.score ?? 0) > (b.evidence.score ?? 0) ? m : b),
    null,
  );
  return best ? { ...best, verified: false } : null;
}

export type TileLayer =
  | "ch.swisstopo.swissimage"
  | "ch.swisstopo.swissimage-product"
  | "ch.swisstopo.zeitreihen"
  | "ch.swisstopo.pixelkarte-grau"
  | "ch.swisstopo.pixelkarte-farbe";

const TILE_EXT: Record<TileLayer, string> = {
  "ch.swisstopo.swissimage": "jpeg",
  "ch.swisstopo.swissimage-product": "jpeg", // aerial photo time series, TIME = year
  "ch.swisstopo.zeitreihen": "png",
  "ch.swisstopo.pixelkarte-grau": "jpeg",
  "ch.swisstopo.pixelkarte-farbe": "jpeg",
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

// --- live analysis (live mode, build step 8) ---

/** POST /analyze. fresh bypasses the backend cache (a cache hit returns a job that is already done). */
export async function startAnalysis(photoId: string, fresh = false): Promise<{ job_id: string; photo_id: string }> {
  const url = `${API_URL}/analyze${query({ fresh: fresh ? 1 : undefined })}`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ photo_id: photoId }),
    });
  } catch {
    throw new ApiError(0, url);
  }
  if (!res.ok) throw new ApiError(res.status, url);
  return res.json();
}

export interface AnalysisHandlers {
  onTrace: (item: TraceItem) => void;
  /** The final AnalysisResult; status "error" carries a German message in `error`. */
  onResult: (result: AnalysisResult) => void;
  /** Neither the stream nor polling reach the backend any more. */
  onError: (e: unknown) => void;
}

const POLL_MS = 1000;

/**
 * Follows a job: SSE (`event: trace` per step, then `event: result`) on /analyze/{job_id}/events.
 * If the stream breaks before the result, it falls back to polling GET /analyze/{job_id} every second
 * (question 3.1). Trace items arrive at most once per step. Returns a cancel function.
 */
export function followAnalysis(jobId: string, h: AnalysisHandlers): () => void {
  if (MODE === "mock") return followMockJob(jobId, h);
  let done = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const seen = new Set<number>();

  const trace = (item: TraceItem) => {
    if (done || seen.has(item.step)) return;
    seen.add(item.step);
    h.onTrace(item);
  };
  const finish = (result: AnalysisResult) => {
    if (done) return;
    result.trace?.forEach(trace); // steps the stream may have missed
    done = true;
    es.close();
    // Lists that asked before the job finished cached null for this photo.
    if (result.status !== "error") resultCache.set(result.photo_id, result);
    h.onResult(result);
  };

  const poll = async () => {
    if (done) return;
    try {
      const snap = await getJson<AnalysisResult>(`${API_URL}/analyze/${enc(jobId)}`);
      if (snap.status === "running" || snap.status === "queued") {
        snap.trace?.forEach(trace);
        timer = setTimeout(poll, POLL_MS);
      } else finish(snap);
    } catch (e) {
      if (done) return;
      done = true;
      h.onError(e);
    }
  };

  const es = new EventSource(`${API_URL}/analyze/${enc(jobId)}/events`);
  es.addEventListener("trace", (ev) => trace(JSON.parse((ev as MessageEvent).data)));
  es.addEventListener("result", (ev) => finish(JSON.parse((ev as MessageEvent).data)));
  // EventSource would reconnect on its own and replay the job from step 1; poll instead.
  es.onerror = () => {
    if (done) return;
    es.close();
    poll();
  };

  return () => {
    done = true;
    es.close();
    if (timer) clearTimeout(timer);
  };
}

// --- trace replay (mock + demo mode) ---

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

// --- batch upload (frontend/context/UPLOAD_PLAN.md) ---

async function send<T>(url: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError(0, url);
  }
  if (!res.ok) throw new ApiError(res.status, url);
  return (await res.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return send<T>(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

interface MockUpload {
  record: PhotoRecord;
  /** Object URL of the uploaded file, so the mock desk shows the real image. */
  url: string;
  result: AnalysisResult | null;
}

/** Mock mode keeps uploads in memory, so the whole batch flow runs without a backend. */
const mockUploads = new Map<string, MockUpload>();
/** Mock job id -> photo id. */
const mockJobs = new Map<string, string>();
let mockSeq = 0;
const MOCK_JOB_MS: [number, number] = [1500, 4500];

/** Shaped like the backend's catalogue.upload_record: the file name is the title, no archive fields. */
function mockUploadRecord(id: string, fileName: string): PhotoRecord {
  return {
    id,
    source: "upload",
    source_id: id.slice("upload:".length),
    source_url: null,
    signature: null,
    collection: null,
    kind: "unknown",
    title: fileName,
    date: { raw: null, year_from: null, year_to: null, approximate: false },
    places: [],
    municipality: null,
    location: null,
    camera: null,
    photographer: null,
    license: { code: "upload", credit: "Hochgeladen", url: null },
    image: null,
    parent_id: null,
    crop_bbox: null,
    split: "none",
    raw: {},
  };
}

/** The mock challenge results in turn (sure + confirmed, Prüfung nötig, nicht bestimmbar), unreviewed. */
function mockUploadResult(n: number, photoId: string): AnalysisResult {
  const all = Object.values(MOCK_CHALLENGE_RESULTS);
  const base = all[n % all.length];
  return { ...base, photo_id: photoId, run_id: `mock-${n}`, review: null, created_at: new Date().toISOString() };
}

/**
 * A mock job plays the trace of its mock result step by step, then finishes; every 7th fails after a few
 * seconds instead, so the error state can be shown.
 */
function followMockJob(jobId: string, h: AnalysisHandlers): () => void {
  const photoId = mockJobs.get(jobId);
  const upload = photoId ? mockUploads.get(photoId) : undefined;
  let cancelled = false;
  if (!photoId || !upload) {
    setTimeout(() => !cancelled && h.onError(new ApiError(404, `/analyze/${enc(jobId)}`)), 0);
    return () => (cancelled = true);
  }
  const n = Number(jobId.slice("mockjob-".length));
  const result = mockUploadResult(n, photoId);
  if (n % 7 === 6) {
    const [min, max] = MOCK_JOB_MS;
    const timer = setTimeout(
      () => !cancelled && h.onResult({ ...result, status: "error", error: "Die Analyse ist fehlgeschlagen." }),
      min + Math.random() * (max - min),
    );
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }
  const stop = replayTrace(result.trace ?? [], h.onTrace, () => {
    if (cancelled) return;
    upload.result = result;
    resultCache.set(photoId, result);
    h.onResult(result);
  });
  return () => {
    cancelled = true;
    stop();
  };
}

/**
 * POST /analyze with a file (multipart "file", filename = path in the ZIP). The backend stores it as
 * upload:<sha1>: the same image gives the same id, so a photo analysed before comes back at once (cache).
 */
export async function uploadPhoto(file: Blob, fileName: string): Promise<{ job_id: string; photo_id: string }> {
  if (MODE === "mock") {
    const n = mockSeq++;
    const photo_id = `upload:mock${String(n).padStart(8, "0")}`;
    const job_id = `mockjob-${n}`;
    mockUploads.set(photo_id, { record: mockUploadRecord(photo_id, fileName), url: URL.createObjectURL(file), result: null });
    mockJobs.set(job_id, photo_id);
    return { job_id, photo_id };
  }
  const form = new FormData();
  form.append("file", file, fileName);
  return send(`${API_URL}/analyze`, { method: "POST", body: form });
}

let batchProbe: Promise<boolean> | null = null;

/**
 * Whether the backend runs batches (GET /batches). 404 / 405: not yet, this browser runs them over
 * POST /analyze (the client runner). Other errors are thrown and probed again next time.
 */
export function serverBatches(): Promise<boolean> {
  if (MODE === "mock") return Promise.resolve(false);
  batchProbe ??= backend<unknown>("/batches").then(
    () => true,
    (e: unknown) => {
      batchProbe = null;
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return false;
      throw e;
    },
  );
  return batchProbe;
}

export async function listServerBatches(): Promise<Batch[]> {
  const r = await backend<Batch[] | { items: Batch[] }>("/batches");
  return Array.isArray(r) ? r : r.items;
}

export function getServerBatch(id: string): Promise<Batch> {
  return backend<Batch>(`/batches/${enc(id)}`);
}

export function createServerBatch(name: string, skipped: { file_name: string; reason: string }[]): Promise<Batch> {
  return postJson<Batch>("/batches", { name, skipped });
}

/** One chunk of files (field "files" repeated, filename = path in the ZIP); the server queues them. */
export function addServerFiles(id: string, files: { file_name: string; file: Blob }[]): Promise<Batch> {
  const form = new FormData();
  for (const f of files) form.append("files", f.file, f.file_name);
  return send<Batch>(`${API_URL}/batches/${enc(id)}/files`, { method: "POST", body: form });
}

/** Queues failed items again; no names = every item with status error. */
export function retryServerBatch(id: string, fileNames?: string[]): Promise<Batch> {
  return postJson<Batch>(`/batches/${enc(id)}/retry`, fileNames ? { file_names: fileNames } : {});
}

/** Images unchanged under their file names plus metadaten.xlsx (server runner only). */
export function exportZipUrl(batchId: string): string {
  return `${API_URL}/export.zip${query({ batch: batchId })}`;
}
