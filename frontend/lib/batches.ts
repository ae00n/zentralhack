// Batches (UPLOAD_PLAN step 1): one store for both runners. "server" when the backend has /batches: it runs
// the queue, this module uploads the files in chunks and polls GET /batches/{id}. "client" otherwise: this
// browser sends each image to POST /analyze, at most CONCURRENCY at a time, and follows the job.
// Client batches are kept in localStorage (not in mock mode, whose uploads only live in memory); the files
// themselves only in memory, so a reload marks uploads that had not started as interrupted, while running
// jobs are followed again. Module state like reviewQueue; pages subscribe with useBatches().
import { useEffect, useSyncExternalStore } from "react";
import {
  MODE,
  addServerFiles,
  createServerBatch,
  errorText,
  followAnalysis,
  getResult,
  getServerBatch,
  listServerBatches,
  retryServerBatch,
  serverBatches,
  uploadPhoto,
} from "./api";
import type { PickedFile, SkippedFile } from "./collect";
import type { AnalysisResult, Batch, BatchItem, BatchItemStatus } from "./types";

const CONCURRENCY = 3;
/** Files per POST /batches/{id}/files. */
const CHUNK = 8;
const POLL_MS = 2000;
const STORAGE_KEY = "batches-v1";
// Medians of the 258 results in agent/reports/results.zip (24.10.).
const SECONDS_PER_PHOTO = 54;
const USD_PER_PHOTO = 0.19;
// These errors hit every later photo too (jobs.py _german_error): stop the rest of the batch at once.
const FATAL = /Kostenlimit|API-Schlüssel/;
const INTERRUPTED = "Upload unterbrochen: Datei bitte erneut hochladen";

const state = { batches: [] as Batch[], version: 0, loaded: false };
/** Files not yet stored by the backend, by fileKey(). Memory only. */
const files = new Map<string, Blob>();
const listeners = new Set<() => void>();
const polling = new Set<string>();
let active = 0;

function fileKey(batchId: string, fileName: string): string {
  return `${batchId}\n${fileName}`;
}

function now(): string {
  return new Date().toISOString().replace(/\.\d+Z$/, "Z");
}

function emit() {
  state.version++;
  persist();
  listeners.forEach((l) => l());
}

function persist() {
  if (MODE === "mock" || typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.batches.filter((b) => b.runner === "client")));
  } catch {
    // No storage (private window): the batch lives until the tab closes.
  }
}

function restore(): Batch[] {
  if (MODE === "mock") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Batch[]) : [];
  } catch {
    return [];
  }
}

function byNewest(a: Batch, b: Batch): number {
  return b.created_at.localeCompare(a.created_at);
}

function putBatch(batch: Batch) {
  const known = state.batches.some((b) => b.id === batch.id);
  state.batches = known ? state.batches.map((b) => (b.id === batch.id ? batch : b)) : [batch, ...state.batches].sort(byNewest);
  emit();
}

function patchItem(batchId: string, fileName: string, changes: Partial<BatchItem>) {
  state.batches = state.batches.map((b) =>
    b.id !== batchId ? b : { ...b, items: b.items.map((i) => (i.file_name === fileName ? { ...i, ...changes } : i)) },
  );
  emit();
}

function item(file_name: string, status: BatchItemStatus, size = 0, error: string | null = null): BatchItem {
  return { file_name, size, photo_id: null, job_id: null, status, error };
}

/**
 * A server answer covers only the files it has received: keep our placeholders for the rest (still
 * uploading, failed to upload), and the skipped ones in case the server does not echo them.
 */
function merge(server: Batch): Batch {
  const local = state.batches.find((b) => b.id === server.id);
  if (!local) return server;
  const names = new Set(server.items.map((i) => i.file_name));
  const keep: BatchItemStatus[] = ["uploading", "error", "skipped"];
  const pending = local.items.filter((i) => !names.has(i.file_name) && keep.includes(i.status));
  return { ...server, items: [...server.items, ...pending] };
}

function unfinished(b: Batch): boolean {
  return b.items.some((i) => i.status === "queued" || i.status === "uploading" || i.status === "running");
}

// --- client runner ---

function nextQueued(): { batchId: string; fileName: string } | null {
  // Oldest batch first.
  for (const b of [...state.batches].reverse()) {
    if (b.runner !== "client") continue;
    const i = b.items.find((x) => x.status === "queued");
    if (i) return { batchId: b.id, fileName: i.file_name };
  }
  return null;
}

function pump() {
  while (active < CONCURRENCY) {
    const next = nextQueued();
    if (!next) return;
    active++;
    // Marked before the await, so the next loop round does not pick the same item.
    patchItem(next.batchId, next.fileName, { status: "uploading", error: null });
    void runClient(next.batchId, next.fileName).finally(() => {
      active--;
      pump();
    });
  }
}

async function runClient(batchId: string, fileName: string): Promise<void> {
  const blob = files.get(fileKey(batchId, fileName));
  if (!blob) return patchItem(batchId, fileName, { status: "error", error: INTERRUPTED });
  let started: { job_id: string; photo_id: string };
  try {
    started = await uploadPhoto(blob, fileName);
  } catch (e) {
    return patchItem(batchId, fileName, { status: "error", error: `Upload fehlgeschlagen: ${errorText(e)}` });
  }
  patchItem(batchId, fileName, { status: "running", photo_id: started.photo_id, job_id: started.job_id });
  await follow(batchId, fileName, started.job_id, started.photo_id);
}

/** Follows a job to its end. A job the backend forgot (restart) still counts as done when a result is cached. */
function follow(batchId: string, fileName: string, jobId: string, photoId: string | null): Promise<void> {
  return new Promise((resolve) => {
    followAnalysis(jobId, {
      onTrace: () => {},
      onResult: (r) => {
        settle(batchId, fileName, r);
        resolve();
      },
      onError: async (e) => {
        const cached = photoId ? await getResult(photoId).catch(() => null) : null;
        if (cached) settle(batchId, fileName, cached);
        else patchItem(batchId, fileName, { status: "error", error: `Analyse unterbrochen: ${errorText(e)}` });
        resolve();
      },
    });
  });
}

function settle(batchId: string, fileName: string, r: AnalysisResult) {
  if (r.status !== "error") {
    files.delete(fileKey(batchId, fileName));
    patchItem(batchId, fileName, { status: "done", error: null });
    const cost = r.usage?.cost_usd ?? 0;
    if (!cost) return;
    state.batches = state.batches.map((b) => (b.id === batchId ? { ...b, cost_usd: (b.cost_usd ?? 0) + cost } : b));
    return emit();
  }
  const msg = r.error || "Die Analyse ist fehlgeschlagen.";
  patchItem(batchId, fileName, { status: "error", error: msg });
  if (!FATAL.test(msg)) return;
  state.batches = state.batches.map((b) =>
    b.id !== batchId ? b : { ...b, items: b.items.map((i) => (i.status === "queued" ? { ...i, status: "error", error: msg } : i)) },
  );
  emit();
}

// --- server runner ---

async function uploadChunks(batchId: string, images: PickedFile[]): Promise<void> {
  for (let i = 0; i < images.length; i += CHUNK) {
    const chunk = images.slice(i, i + CHUNK);
    chunk.forEach((p) => patchItem(batchId, p.file_name, { status: "uploading", error: null }));
    try {
      putBatch(merge(await addServerFiles(batchId, chunk)));
      chunk.forEach((p) => files.delete(fileKey(batchId, p.file_name)));
    } catch (e) {
      const error = `Upload fehlgeschlagen: ${errorText(e)}`;
      chunk.forEach((p) => patchItem(batchId, p.file_name, { status: "error", error }));
    }
  }
  poll(batchId);
}

function poll(batchId: string) {
  if (polling.has(batchId)) return;
  polling.add(batchId);
  const tick = async () => {
    if (!state.batches.some((b) => b.id === batchId)) return polling.delete(batchId);
    try {
      const b = merge(await getServerBatch(batchId));
      putBatch(b);
      if (!unfinished(b)) return polling.delete(batchId);
    } catch {
      // Backend briefly away: keep polling.
    }
    setTimeout(tick, POLL_MS);
  };
  void tick();
}

// --- public ---

/** Loads once per page: client batches from localStorage (running jobs are followed again), server batches. */
function load() {
  if (state.loaded || typeof window === "undefined") return;
  state.loaded = true;
  const local = restore().map((b) => ({
    ...b,
    items: b.items.map((i) => (i.status === "queued" || i.status === "uploading" ? { ...i, status: "error" as const, error: INTERRUPTED } : i)),
  }));
  state.batches = local.sort(byNewest);
  emit();
  for (const b of local) for (const i of b.items) if (i.status === "running" && i.job_id) void follow(b.id, i.file_name, i.job_id, i.photo_id);
  serverBatches()
    .then(async (ok) => {
      if (!ok) return;
      for (const b of await listServerBatches()) {
        putBatch(b);
        if (unfinished(b)) poll(b.id);
      }
    })
    .catch(() => {
      // Backend not reachable: only the local batches show.
    });
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** All batches, newest first; re-renders on every change. */
export function useBatches(): Batch[] {
  useSyncExternalStore(subscribe, () => state.version, () => 0);
  useEffect(load, []);
  return state.batches;
}

export function getBatch(id: string): Batch | null {
  return state.batches.find((b) => b.id === id) ?? null;
}

/**
 * Starts a batch and returns its id as soon as it exists; the uploads run in the background. Skipped files
 * are part of the batch (status "skipped"), so the overview can say what was left out and why.
 */
export async function startBatch(name: string, images: PickedFile[], skipped: SkippedFile[]): Promise<string> {
  const skippedItems = skipped.map((s) => item(s.file_name, "skipped", 0, s.reason));
  if (await serverBatches().catch(() => false)) {
    const created = await createServerBatch(name, skipped);
    images.forEach((p) => files.set(fileKey(created.id, p.file_name), p.file));
    // The files show at once; each chunk's answer replaces the placeholders it covers.
    putBatch({ ...created, items: [...images.map((p) => item(p.file_name, "uploading", p.size)), ...skippedItems] });
    void uploadChunks(created.id, images);
    return created.id;
  }
  const id = `local-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  images.forEach((p) => files.set(fileKey(id, p.file_name), p.file));
  putBatch({
    id,
    name,
    created_at: now(),
    runner: "client",
    items: [...images.map((p) => item(p.file_name, "queued", p.size)), ...skippedItems],
    cost_usd: 0,
  });
  pump();
  return id;
}

/** Whether "Erneut versuchen" can work: the file is still in memory, or the backend already has the image. */
export function canRetry(batch: Batch, i: BatchItem): boolean {
  if (i.status !== "error") return false;
  if (files.has(fileKey(batch.id, i.file_name))) return true;
  return batch.runner === "server" && i.photo_id !== null;
}

/** Erneut versuchen for one item, or for every failed item of the batch that can be retried. */
export function retry(batchId: string, fileName?: string) {
  const batch = getBatch(batchId);
  if (!batch) return;
  const targets = batch.items.filter((i) => canRetry(batch, i) && (!fileName || i.file_name === fileName));
  if (batch.runner === "client") {
    targets.forEach((i) => patchItem(batchId, i.file_name, { status: "queued", error: null, job_id: null }));
    return pump();
  }
  // Server: files that never arrived are sent again, the rest is queued again by the server.
  const resend = targets
    .filter((i) => i.photo_id === null)
    .map((i) => ({ file_name: i.file_name, size: i.size, file: files.get(fileKey(batchId, i.file_name)) as Blob }));
  if (resend.length) void uploadChunks(batchId, resend);
  const onServer = targets.filter((i) => i.photo_id !== null).map((i) => i.file_name);
  if (!onServer.length) return;
  onServer.forEach((n) => patchItem(batchId, n, { status: "queued", error: null }));
  retryServerBatch(batchId, onServer)
    .then((b) => {
      putBatch(merge(b));
      poll(batchId);
    })
    .catch((e: unknown) => onServer.forEach((n) => patchItem(batchId, n, { status: "error", error: errorText(e) })));
}

/** Removes a batch from this browser (a server batch shows again on the next load). */
export function removeBatch(id: string) {
  for (const k of [...files.keys()]) if (k.startsWith(`${id}\n`)) files.delete(k);
  state.batches = state.batches.filter((b) => b.id !== id);
  emit();
}

export type BatchCounts = Record<BatchItemStatus, number> & { total: number };

export function batchCounts(b: Batch): BatchCounts {
  const c: BatchCounts = { total: b.items.length, queued: 0, uploading: 0, running: 0, done: 0, error: 0, skipped: 0 };
  for (const i of b.items) c[i.status]++;
  return c;
}

export function isRunning(b: Batch): boolean {
  return unfinished(b);
}

/** Photos of the batch with a result, in batch order (desk, review queue, export ?ids=). */
export function batchPhotoIds(b: Batch): string[] {
  return b.items.filter((i) => i.status === "done" && i.photo_id).map((i) => i.photo_id as string);
}

/** Time and cost for n photos at the measured medians, CONCURRENCY at a time. */
export function estimate(n: number): { minutes: number; usd: number } {
  return { minutes: n ? Math.max(1, Math.ceil((n * SECONDS_PER_PHOTO) / CONCURRENCY / 60)) : 0, usd: n * USD_PER_PHOTO };
}

/** Name proposal: the ZIP or folder name, else "Upload 24.10.2026 14:05". */
export function suggestName(input: File[]): string {
  const first = input[0];
  const folder = first?.webkitRelativePath?.split("/")[0];
  if (input.length === 1 && /\.zip$/i.test(first.name)) return first.name.replace(/\.zip$/i, "");
  if (folder && input.every((f) => f.webkitRelativePath.startsWith(`${folder}/`))) return folder;
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `Upload ${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
