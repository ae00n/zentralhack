// Review decisions (FRONTPAGE_PLAN 5, "Review"). A decision shows at once (optimistic), but its POST is
// held for 6 s or until the next decision, so Rückgängig works client-side. Module state, so it survives
// moving to the next photo; pages subscribe with useReviewStore().
import { useSyncExternalStore } from "react";
import { toast as sonner } from "sonner";
import { postReview, type ReviewBody } from "./api";
import type { AnalysisResult, Review } from "./types";

const HOLD_MS = 6000;

interface Pending {
  photoId: string;
  signature: string;
  review: Review;
  /** Review before this decision (the server's or an earlier local one), restored on undo. */
  prev: Review | null | undefined;
  timer: ReturnType<typeof setTimeout>;
}

export interface Toast {
  text: string;
  undoable: boolean;
  error?: boolean;
  /** The "Rückgängig: …" note gets its own slot: sonner closes the decision toast after its action. */
  undoNote?: boolean;
}

interface State {
  /** Local review per photo; wins over the server's until the POST has landed. */
  overrides: Map<string, Review | null>;
  toast: Toast | null;
  /** Timestamps of decisions this session, for "ca. 6 Min. übrig". */
  decisions: number[];
  skipped: Set<string>;
  version: number;
}

const state: State = { overrides: new Map(), toast: null, decisions: [], skipped: new Set(), version: 0 };
let pending: Pending | null = null;
/** One toast slot: a new decision replaces the previous toast (sonner, bottom centre). */
const TOAST_ID = "review";
const UNDO_ID = "review-undo";
const listeners = new Set<() => void>();

function emit() {
  state.version++;
  listeners.forEach((l) => l());
}

function showToast(t: Toast | null) {
  state.toast = t;
  if (!t) sonner.dismiss(TOAST_ID);
  else if (t.undoNote) sonner(t.text, { id: UNDO_ID, duration: 2500 });
  else if (t.error) sonner.error(t.text, { id: TOAST_ID, duration: HOLD_MS });
  else
    sonner(t.text, {
      id: TOAST_ID,
      duration: HOLD_MS,
      action: t.undoable ? { label: "Rückgängig (⌫)", onClick: () => void undo() } : undefined,
    });
  emit();
}

async function send(p: Pending) {
  try {
    await postReview(p.photoId, { status: p.review.status, fields: p.review.fields, note: p.review.note });
  } catch {
    // Roll the optimistic value back so the screen never shows a decision the server does not have.
    if (p.prev === undefined) state.overrides.delete(p.photoId);
    else state.overrides.set(p.photoId, p.prev);
    showToast({ text: "Speichern fehlgeschlagen, bitte erneut versuchen", undoable: false, error: true });
  }
}

/** Sends the held decision now (next decision, leaving the page). */
export function flush() {
  if (!pending) return;
  const p = pending;
  pending = null;
  clearTimeout(p.timer);
  void send(p);
  // The decision is on its way: the toast stays, without the undo action.
  if (state.toast?.undoable) showToast({ ...state.toast, undoable: false });
}

if (typeof window !== "undefined") window.addEventListener("pagehide", flush);

/** The review that counts for a result: a local decision, else the server's. */
export function withLocalReview(result: AnalysisResult): AnalysisResult;
export function withLocalReview(result: AnalysisResult | null): AnalysisResult | null;
export function withLocalReview(result: AnalysisResult | null): AnalysisResult | null {
  if (!result || !state.overrides.has(result.photo_id)) return result;
  return { ...result, review: state.overrides.get(result.photo_id) ?? null };
}

/** Bestätigen or Korrigieren. Holds the POST; the toast offers Rückgängig. */
export function decide(result: AnalysisResult, signature: string, body: ReviewBody) {
  flush();
  const id = result.photo_id;
  const prev = state.overrides.has(id) ? state.overrides.get(id) : undefined;
  const review: Review = {
    status: body.status,
    fields: body.fields ?? {},
    note: body.note ?? null,
    reviewed_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  };
  state.overrides.set(id, review);
  state.decisions.push(Date.now());
  state.skipped.delete(id);
  const p: Pending = { photoId: id, signature, review, prev, timer: setTimeout(() => flush(), HOLD_MS) };
  pending = p;
  sonner.dismiss(UNDO_ID);
  const verb = body.status === "korrigiert" ? "Korrigiert" : "Bestätigt";
  showToast({ text: `${verb}: ${signature}`, undoable: true });
}

/** Rückgängig: only while the decision is still held. */
export function undo(): boolean {
  if (!pending) return false;
  const p = pending;
  pending = null;
  clearTimeout(p.timer);
  if (p.prev === undefined) state.overrides.delete(p.photoId);
  else state.overrides.set(p.photoId, p.prev);
  state.decisions.pop();
  sonner.dismiss(TOAST_ID);
  showToast({ text: `Rückgängig: ${p.signature}`, undoable: false, undoNote: true });
  return true;
}

let advanceTo: string | null = null;
let consumed: { id: string; at: number } | null = null;

/** Moving on through the review queue: that photo shows its result at once, without the replay. */
export function markAdvance(photoId: string) {
  advanceTo = photoId;
}

/**
 * True when the detail page loads the photo the queue just moved to. Tolerates the second effect run
 * of dev StrictMode (same id within a second); opening the photo later from the desk replays again.
 */
export function consumeAdvance(photoId: string): boolean {
  if (advanceTo === photoId) {
    advanceTo = null;
    consumed = { id: photoId, at: Date.now() };
    return true;
  }
  return consumed?.id === photoId && Date.now() - consumed.at < 1000;
}

export function skip(photoId: string) {
  state.skipped.add(photoId);
  emit();
}

export function isSkipped(photoId: string): boolean {
  return state.skipped.has(photoId);
}

/** Median seconds per decision over the last 10, or null with fewer than 3 decisions. */
export function medianSecondsPerDecision(): number | null {
  const t = state.decisions.slice(-11);
  if (t.length < 3) return null;
  const gaps = t.slice(1).map((x, i) => (x - t[i]) / 1000).sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)];
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Re-renders on every store change; read the values through the helpers above. */
export function useReviewStore(): { toast: Toast | null; version: number } {
  const version = useSyncExternalStore(subscribe, () => state.version, () => 0);
  return { toast: state.toast, version };
}
