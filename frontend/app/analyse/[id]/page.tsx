"use client";

// Foto (FRONTPAGE_PLAN 5): breadcrumb with Vorheriges / Nächstes, photo | Erschliessung, then the trace
// ("So entsteht das Ergebnis") and the compact map. The Zeitreise map is not shown here in v3.
// Mock and demo mode replay the cached trace (step 5). Live mode shows a cached result at once and
// streams a new analysis over SSE when asked (step 8); it never starts one on its own (costs money).
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ArchiveMatch from "@/components/analyse/ArchiveMatch";
import ExcelRow from "@/components/analyse/ExcelRow";
import MapPanel from "@/components/analyse/MapPanel";
import PhotoPanel from "@/components/analyse/PhotoPanel";
import ResultPanel, { type EditState } from "@/components/analyse/ResultPanel";
import ReviewBar from "@/components/analyse/ReviewBar";
import SeriesStrip from "@/components/analyse/SeriesStrip";
import TraceLog from "@/components/analyse/TraceLog";
import ReviewToast from "@/components/ReviewToast";
import {
  ApiError,
  MODE,
  errorText,
  followAnalysis,
  exportXlsxUrl,
  getDemo,
  getGemeinden,
  getPhoto,
  getResult,
  listChallenge,
  listResults,
  replayTrace,
  startAnalysis,
} from "@/lib/api";
import { countItems, modelClass } from "@/lib/desk";
import { analyseHref, isEmptyValue } from "@/lib/format";
import { REVIEW_FIELDS, aiValue, effectiveValue } from "@/lib/review";
import {
  consumeAdvance,
  decide,
  isSkipped,
  markAdvance,
  medianSecondsPerDecision,
  skip,
  undo,
  useReviewStore,
  withLocalReview,
} from "@/lib/reviewQueue";
import type { AnalysisResult, PhotoRecord, ReviewField, TraceItem } from "@/lib/types";

/** Draft text for an input: lists as "a; b", empty as "". */
function draftOf(v: string | string[] | null): string {
  return v === null ? "" : Array.isArray(v) ? v.join("; ") : v;
}

/** Back from the input: lists split on ";", empty = null (nicht bestimmbar). */
function parseDraft(key: ReviewField, text: string): string | string[] | null {
  if (key === "buildings" || key === "landscape_features") {
    const list = text.split(";").map((x) => x.trim()).filter(Boolean);
    return list.length ? list : null;
  }
  return text.trim() || null;
}

function same(a: string | string[] | null, b: string | string[] | null): boolean {
  return draftOf(isEmptyValue(a) ? null : a) === draftOf(isEmptyValue(b) ? null : b);
}

/** The field the archivist should look at first: lowest confidence among the brief's five. */
function weakestField(result: AnalysisResult): ReviewField {
  return REVIEW_FIELDS.reduce((w, k) =>
    (result.fields[k]?.confidence ?? 0) < (result.fields[w]?.confidence ?? 0) ? k : w,
  );
}

function decodeId(raw: string | string[] | undefined): string {
  const s = Array.isArray(raw) ? raw[0] : (raw ?? "");
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export default function AnalysePage() {
  const id = decodeId(useParams<{ id: string }>().id);
  const [record, setRecord] = useState<PhotoRecord | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<TraceItem[]>([]);
  const [replaying, setReplaying] = useState(false);
  const [queue, setQueue] = useState<string[]>([]);
  // Live mode: an analysis is streaming, or it ended with an error (German text).
  const [analysing, setAnalysing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const cancelReplay = useRef<(() => void) | undefined>(undefined);
  const cancelLive = useRef<(() => void) | undefined>(undefined);
  const router = useRouter();
  useReviewStore(); // re-render on decisions, undo and toasts
  const [queueResults, setQueueResults] = useState<Map<string, AnalysisResult | null>>(new Map());
  const [gemeinden, setGemeinden] = useState<string[]>([]);
  const [edit, setEdit] = useState<{ drafts: Record<ReviewField, string>; focus: ReviewField } | null>(null);
  const [ended, setEnded] = useState(false);
  const [announce, setAnnounce] = useState("");
  // Phone: the finished trace starts collapsed (plan 5). Read once on the client.
  const [wide, setWide] = useState(true);
  useEffect(() => setWide(window.matchMedia("(min-width: 1024px)").matches), []);
  const lastKey = useRef(0);
  const focusedFor = useRef<string | null>(null);

  const startLive = useCallback(
    async (fresh: boolean) => {
      cancelLive.current?.();
      let cancelled = false;
      cancelLive.current = () => {
        cancelled = true;
      };
      setResult(null);
      setMissing(false);
      setFailure(null);
      setSteps([]);
      setAnalysing(true);
      try {
        const job = await startAnalysis(id, fresh);
        if (cancelled) return;
        cancelLive.current = followAnalysis(job.job_id, {
          onTrace: (item) => setSteps((prev) => [...prev, item]),
          onResult: (res) => {
            setAnalysing(false);
            if (res.status === "error") {
              setFailure(res.error || "Die Analyse ist fehlgeschlagen.");
              setSteps(res.trace ?? []);
            } else {
              setResult(res);
              setSteps(res.trace ?? []);
            }
          },
          onError: (e) => {
            setAnalysing(false);
            setFailure(`Verbindung zur Analyse verloren: ${errorText(e)}.`);
          },
        });
      } catch (e) {
        if (cancelled) return;
        setAnalysing(false);
        setFailure(`Analyse konnte nicht starten: ${errorText(e)}.`);
      }
    },
    [id],
  );

  const startReplay = useCallback((res: AnalysisResult) => {
    cancelReplay.current?.();
    setSteps([]);
    setReplaying(true);
    cancelReplay.current = replayTrace(
      res.trace,
      (item) => setSteps((prev) => [...prev, item]),
      () => setReplaying(false),
    );
  }, []);

  // Vorheriges / Nächstes: the Prio-1 list for challenge photos (all 603 when the photo is not in it),
  // the pitch order of /demo for anything else.
  useEffect(() => {
    let stale = false;
    const load = async (): Promise<string[]> => {
      if (!id.startsWith("challenge:")) return (await getDemo()).map((d) => d.id);
      const prio = (await listChallenge({ priority: 1 })).map((r) => r.id);
      return prio.includes(id) ? prio : (await listChallenge()).map((r) => r.id);
    };
    load()
      .then(async (ids) => {
        if (stale) return;
        setQueue(ids);
        const res = await listResults(ids);
        if (!stale) setQueueResults(res);
      })
      .catch(() => !stale && setQueue([]));
    return () => {
      stale = true;
    };
  }, [id]);

  useEffect(() => {
    // Set by the cleanup: a response for an old effect run (dev StrictMode runs effects twice,
    // or the id changed) must not start a second replay.
    let stale = false;
    setRecord(null);
    setResult(null);
    setMissing(false);
    setError(null);
    setSteps([]);
    setAnalysing(false);
    setFailure(null);
    setEdit(null);
    setEnded(false);
    lastKey.current = 0;
    // Moving on with Enter / arrows / N shows the next result at once; the replay is for arriving from the desk.
    const advancing = consumeAdvance(id);

    Promise.all([getPhoto(id), getResult(id)])
      .then(([rec, res]) => {
        if (stale) return;
        setRecord(rec);
        if (!res) {
          setMissing(true);
          return;
        }
        setResult(res);
        if (MODE !== "live" && res.trace?.length && !advancing) startReplay(res);
        else setSteps(res.trace ?? []);
      })
      .catch((e: unknown) =>
        !stale &&
        setError(
          e instanceof ApiError && e.status === 404
            ? "Dieses Foto gibt es nicht."
            : `Foto konnte nicht geladen werden: ${errorText(e)}.`,
        ),
      );

    return () => {
      stale = true;
      cancelReplay.current?.();
      cancelLive.current?.(); // the job keeps running on the server; only the stream closes
    };
  }, [id, startReplay]);

  const skipReplay = () => {
    if (!result) return;
    cancelReplay.current?.();
    setSteps(result.trace ?? []);
    setReplaying(false);
  };

  useEffect(() => {
    getGemeinden().then(setGemeinden);
  }, []);

  // The review that counts: a held or sent local decision, else the server's.
  const shown = result ? withLocalReview(result) : null;
  const decided = shown?.review?.status === "bestaetigt" || shown?.review?.status === "korrigiert";

  const showResult = shown && !replaying && !analysing;
  const running = replaying || analysing;
  const canRunLive = MODE === "live" && record && !analysing;
  // Nothing of the result shows before the replay ends, the map included.
  const coords = showResult ? shown.fields.coordinates?.value : null;
  const canReplay = MODE !== "live" && showResult && shown.trace?.length > 0;
  const pos = queue.indexOf(id);
  const prev = pos > 0 ? queue[pos - 1] : undefined;
  const next = pos >= 0 ? queue[pos + 1] : undefined;
  const signature = record?.signature ?? id;
  // Überspringen puts a photo at the end of the queue: the next unskipped one after this, then the skipped.
  const nextInQueue =
    pos >= 0
      ? (queue.slice(pos + 1).find((q) => !isSkipped(q)) ?? queue.find((q) => q !== id && isSkipped(q)))
      : undefined;

  // Progress over the queue (Prio 1): "12 von 50 Prio 1 geprüft · 3 korrigiert · ca. 6 Min. übrig".
  const queueItems = queue.map((q) => ({
    record: { id: q } as PhotoRecord,
    result: withLocalReview(q === id && result ? result : (queueResults.get(q) ?? null)),
  }));
  const progress = countItems(queueItems);
  const skippedCount = queue.filter((q) => isSkipped(q)).length;
  const secs = medianSecondsPerDecision();
  const left = progress.total - progress.reviewed;
  const minutes = secs !== null && left > 0 ? Math.max(1, Math.ceil((left * secs) / 60)) : null;
  const prioQueue = id.startsWith("challenge:") && queue.length > 0;

  const go = (target: string | undefined) => {
    if (!target) return;
    markAdvance(target);
    router.push(analyseHref(target));
  };

  const confirm = () => {
    if (!shown || edit) return;
    if (!decided) decide(shown, signature, { status: "bestaetigt" });
    if (nextInQueue) go(nextInQueue);
    else setEnded(true);
  };

  const startEdit = (focus?: ReviewField) => {
    if (!shown || running) return;
    const drafts = Object.fromEntries(REVIEW_FIELDS.map((k) => [k, draftOf(effectiveValue(shown, k))])) as Record<
      ReviewField,
      string
    >;
    setEdit({ drafts, focus: focus ?? weakestField(shown) });
  };

  const focusHeading = () => setTimeout(() => document.getElementById("erschliessung-heading")?.focus(), 0);

  const saveEdit = () => {
    if (!shown || !edit) return;
    // Every field whose final value differs from the AI value is a correction (keeps earlier ones too).
    const fields: Partial<Record<ReviewField, string | string[] | null>> = {};
    for (const k of REVIEW_FIELDS) {
      const v = parseDraft(k, edit.drafts[k]);
      if (!same(v, aiValue(shown, k))) fields[k] = v;
    }
    const corrected = Object.keys(fields).length > 0;
    decide(shown, signature, corrected ? { status: "korrigiert", fields } : { status: "bestaetigt" });
    setEdit(null);
    focusHeading();
  };

  const cancelEdit = () => {
    setEdit(null);
    focusHeading();
  };

  const doSkip = () => {
    if (!shown) return;
    skip(id);
    if (nextInQueue) go(nextInQueue);
    else setEnded(true);
  };

  // Keys on the review region only (plan 5, rule 1): not in inputs, not during IME, not with modifiers.
  const onKeyDown = (e: React.KeyboardEvent) => {
    const t = e.target as HTMLElement;
    if (e.ctrlKey || e.metaKey || e.altKey || e.nativeEvent.isComposing) return;
    if (t.closest("input, textarea, select, [role=combobox], [contenteditable=true]")) return;
    const now = Date.now();
    if (now - lastKey.current < 150) return; // debounce per photo
    let handled = true;
    switch (e.key) {
      case "Enter":
        if (t.closest("button, a, summary")) return; // a focused control does its own thing
        if (replaying) skipReplay();
        else confirm();
        break;
      case "k":
      case "K":
        startEdit();
        break;
      case "1":
      case "2":
      case "3":
      case "4":
      case "5":
        startEdit(REVIEW_FIELDS[Number(e.key) - 1]);
        break;
      case "ArrowRight":
        go(next);
        break;
      case "ArrowLeft":
        go(prev);
        break;
      case "n":
      case "N":
        doSkip();
        break;
      case "Backspace":
        undo();
        break;
      case "Escape":
        if (edit) cancelEdit();
        else handled = false;
        break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
      lastKey.current = now;
    }
  };

  // Once the result shows: announce the position, and focus the heading, or on "Prüfung nötig" photos the
  // weakest field, so Bestätigen is never preselected there (automation bias, plan 5 rule 7).
  useEffect(() => {
    if (!showResult || !shown || focusedFor.current === id) return;
    focusedFor.current = id;
    if (pos >= 0) setAnnounce(`Foto ${pos + 1} von ${queue.length}`);
    const target =
      modelClass(shown) === "sure"
        ? document.getElementById("erschliessung-heading")
        : document.querySelector<HTMLElement>(`[data-review-field="${weakestField(shown)}"]`);
    target?.focus({ preventScroll: true });
  });

  const editState: EditState | null = edit
    ? {
        drafts: edit.drafts,
        focus: edit.focus,
        gemeinden,
        onChange: (k, v) => setEdit((cur) => (cur ? { ...cur, drafts: { ...cur.drafts, [k]: v } } : cur)),
        onSave: saveEdit,
        onCancel: cancelEdit,
      }
    : null;

  return (
    <>
      <nav aria-label="Brotkrume" className="bg-paper-2">
        <div className="wrapper flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-2.5">
          <ol className="flex items-center gap-1 overflow-x-auto whitespace-nowrap text-small font-bold">
            <li>
              <Link href="/" className="px-1 hover:text-ink-strong hover:underline">
                Arbeitsplatz
              </Link>
            </li>
            {record?.collection && (
              <li className="flex items-center gap-1">
                <ChevronRight size={14} strokeWidth={1.5} className="text-ink-muted" aria-hidden />
                <Link href="/" className="px-1 hover:text-ink-strong hover:underline">
                  {record.collection}
                </Link>
              </li>
            )}
            <li className="flex items-center gap-1">
              <ChevronRight size={14} strokeWidth={1.5} className="text-ink-muted" aria-hidden />
              <span aria-current="page" className="rounded bg-accent px-2 py-0.5 font-mono font-medium text-white">
                {signature}
              </span>
            </li>
          </ol>
          {pos >= 0 && (
            <div className="flex items-center gap-4 text-small">
              {prev ? (
                <Link href={analyseHref(prev)} className="hover:text-ink-strong hover:underline">
                  ← Vorheriges
                </Link>
              ) : (
                <span className="text-ink-muted">← Vorheriges</span>
              )}
              <span className="font-mono text-ink-muted">
                {pos + 1} von {queue.length}
              </span>
              {next ? (
                <Link href={analyseHref(next)} className="hover:text-ink-strong hover:underline">
                  Nächstes →
                </Link>
              ) : (
                <span className="text-ink-muted">Nächstes →</span>
              )}
            </div>
          )}
        </div>
        {prioQueue && (
          <p className="wrapper pb-2.5 text-meta text-ink-muted">
            {progress.reviewed} von {progress.total} Prio 1 geprüft · {progress.corrected} korrigiert
            {minutes !== null && ` · ca. ${minutes} Min. übrig`}
          </p>
        )}
      </nav>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>

      <main className="wrapper py-6" onKeyDown={onKeyDown}>
        {ended && (
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-l-4 border-cert-confirmed bg-paper-2 px-4 py-3">
            <p className="text-body">
              {progress.reviewed === progress.total
                ? `Alle ${progress.total} Prio-1-Fotos geprüft`
                : `Ende der Liste · ${progress.total - progress.reviewed} noch offen`}
              {` · ${progress.confirmed} bestätigt · ${progress.corrected} korrigiert · ${skippedCount} übersprungen`}
            </p>
            <a
              href={exportXlsxUrl({ split: "challenge", priority: 1 })}
              download
              className="rounded bg-accent px-4 py-2 font-bold text-white transition-colors duration-fade hover:bg-accent-hover"
            >
              Excel herunterladen
            </a>
          </div>
        )}
        {error && <p className="text-bad">{error}</p>}
        {!error && !record && <p className="text-ink-muted">Lade Foto ...</p>}

        {record && (
          <>
            {/* Desktop: photo + archive match left, Erschliessung right. Phone order (plan 5): photo,
                fields, review bar, then the archive match. */}
            <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-6 lg:grid-cols-2">
              <div className="min-w-0 lg:col-start-1 lg:row-start-1">
                <PhotoPanel record={record} />
              </div>

              <div className="min-w-0 space-y-6 lg:col-start-2 lg:row-span-2 lg:row-start-1">
                {missing && (
                  <div className="flex flex-wrap items-baseline justify-between gap-3 border-y border-rule py-3">
                    <p className="text-ink-muted">Noch kein Ergebnis für dieses Foto</p>
                    {canRunLive && <StartButton onClick={() => startLive(false)}>Analyse starten</StartButton>}
                  </div>
                )}

                {failure && (
                  <div className="flex flex-wrap items-baseline justify-between gap-3 border-y border-rule py-3">
                    <p className="text-bad">{failure}</p>
                    {canRunLive && <StartButton onClick={() => startLive(true)}>Erneut versuchen</StartButton>}
                  </div>
                )}

                {running && (
                  <div className="flex items-baseline justify-between border-y border-rule py-3">
                    <p className="text-ink-muted">Ort wird bestimmt ...</p>
                    {replaying && (
                      <button type="button" onClick={skipReplay} className="text-small text-ink-muted hover:text-ink-strong">
                        Überspringen
                      </button>
                    )}
                  </div>
                )}
                {/* While it runs, the steps appear where the result will appear. */}
                {running && <TraceLog items={steps} running />}

                {showResult && <ResultPanel result={shown} edit={editState} />}
                {showResult && (
                  // Phone: a bar stuck to the bottom while the fields are on screen (plan 5).
                  <div className="sticky bottom-0 z-10 border-t border-rule bg-paper py-3 lg:static lg:border-0 lg:py-0">
                  <ReviewBar
                    editing={!!edit}
                    decided={decided}
                    onConfirm={confirm}
                    onCorrect={() => startEdit()}
                    onSkip={doSkip}
                    onSave={saveEdit}
                    onCancel={cancelEdit}
                  />
                  </div>
                )}
                {showResult && <SeriesStrip record={record} />}
              </div>
              {showResult && (
                <div className="min-w-0 lg:col-start-1 lg:row-start-2 lg:-mt-2">
                  <ArchiveMatch record={record} result={shown} />
                </div>
              )}
            </div>

            {!running && steps.length > 0 && (
              <section className="relative mt-10 border-t border-rule pt-4">
                <div className="absolute right-0 top-4 flex gap-4 text-small text-ink-muted">
                  {canReplay && (
                    <button type="button" onClick={() => result && startReplay(result)} className="hover:text-ink-strong">
                      Erneut abspielen
                    </button>
                  )}
                  {canRunLive && showResult && (
                    <button type="button" onClick={() => startLive(true)} className="hover:text-ink-strong">
                      Neu analysieren
                    </button>
                  )}
                </div>
                <TraceLog items={steps} running={false} defaultOpen={wide} />
              </section>
            )}

            {showResult && (
              <section className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-8 border-t border-rule pt-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,480px)]">
                <ExcelRow record={record} result={shown} />
                <div>
                <h2 className="text-h3">Karte</h2>
                <div className="mt-3">
                  <MapPanel
                    coords={coords ?? null}
                    emptyText="Ort nicht bestimmbar"
                    startYear={null}
                    photoId={id}
                    zeitreise={false}
                  />
                </div>
                </div>
              </section>
            )}
          </>
        )}
      </main>
      <ReviewToast />
    </>
  );
}

function StartButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-ink px-3 py-1.5 text-meta hover:border-accent hover:text-ink-strong"
    >
      {children}
    </button>
  );
}
