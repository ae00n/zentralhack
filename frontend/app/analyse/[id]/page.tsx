"use client";

// Foto (FRONTPAGE_PLAN 5, layout FRONTPAGE_POLISH 6): a toolbar (breadcrumb, stage tabs Foto | Vergleich |
// Karte, position in the queue), the stage on the left and a 440 px inspector with a sticky review footer.
// Mock and demo mode replay the cached trace (step 5). Live mode shows a cached result at once and
// streams a new analysis over SSE when asked (step 8); it never starts one on its own (costs money).
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
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
import {
  ApiError,
  MODE,
  errorText,
  followAnalysis,
  bestReferenceMatch,
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
import { FOCUS_RING, buttonClass } from "@/components/ui/button";
import Segmented from "@/components/ui/Segmented";
import { cn } from "@/lib/cn";
import { countItems, modelClass } from "@/lib/desk";
import { quietFocus } from "@/lib/quietFocus";
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

type Stage = "foto" | "vergleich" | "karte";

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
  // Stage tab (polish 6): the photo, the archive match, or the map; back to the photo for each new photo.
  const [stage, setStage] = useState<Stage>("foto");
  // Phone: the finished trace starts collapsed (plan 5). Read once on the client.
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
    setStage("foto");
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

  const focusHeading = () => setTimeout(() => quietFocus(document.getElementById("erschliessung-heading")), 0);

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
    quietFocus(target); // no ring until the keyboard is used (polish 6)
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

  const hasMatch = !!(showResult && bestReferenceMatch(shown));
  const stageTabs: { key: Stage; label: string }[] = [
    { key: "foto", label: "Foto" },
    ...(hasMatch ? [{ key: "vergleich" as const, label: "Vergleich" }] : []),
    { key: "karte", label: "Karte" },
  ];
  const activeStage: Stage = stage === "vergleich" && !hasMatch ? "foto" : stage;
  const navButton = "h-8 w-8 px-0";

  return (
    <>
      {/* Toolbar (polish 6): breadcrumb, stage tabs, position in the queue. 44 px, white, hairline. */}
      <nav
        aria-label="Werkzeugleiste"
        className="flex min-h-11 flex-wrap items-center gap-x-4 gap-y-1 border-b border-rule/[0.08] bg-paper px-4 py-1.5"
      >
        {/* Back to the desk with this photo open in the side panel (Said, 24.10.). */}
        <Link
          href={`/?foto=${encodeURIComponent(id)}`}
          className={cn(
            "-ml-1 inline-flex items-center gap-1.5 rounded px-2 py-1 text-ui font-medium text-ink transition-colors duration-hover hover:bg-paper-2",
            FOCUS_RING,
          )}
        >
          <ArrowLeft className="size-4" aria-hidden />
          Zurück
        </Link>
        <ol aria-label="Brotkrume" className="flex min-w-0 items-center gap-1.5 overflow-x-auto whitespace-nowrap text-ui text-ink-muted">
          <li>
            <Link href="/" className={cn("rounded-sm hover:text-ink", FOCUS_RING)}>
              Arbeitsplatz
            </Link>
          </li>
          {record?.collection && (
            <>
              <li aria-hidden>/</li>
              <li>
                <Link href="/" className={cn("rounded-sm hover:text-ink", FOCUS_RING)}>
                  {record.collection}
                </Link>
              </li>
            </>
          )}
          <li aria-hidden>/</li>
          <li aria-current="page" className="font-mono font-medium text-ink">
            {signature}
          </li>
        </ol>

        {record && (
          <Segmented role="tab" label="Ansicht" value={activeStage} onChange={setStage} options={stageTabs} className="lg:mx-auto" />
        )}

        <div className="ml-auto flex items-center gap-1">
          {prioQueue && (
            <span className="mr-2 hidden text-meta tnum text-ink-muted xl:inline">
              {progress.reviewed} von {progress.total} Prio 1 geprüft · {progress.corrected} korrigiert
              {minutes !== null && ` · ca. ${minutes} Min. übrig`}
            </span>
          )}
          {pos >= 0 && (
            <>
              {prev ? (
                <Link href={analyseHref(prev)} aria-label="Vorheriges Foto" className={buttonClass("ghost", navButton)}>
                  <ChevronLeft size={16} strokeWidth={1.75} />
                </Link>
              ) : (
                <span aria-hidden className={cn(buttonClass("ghost", navButton), "opacity-40")}>
                  <ChevronLeft size={16} strokeWidth={1.75} />
                </span>
              )}
              <span className="text-ui tnum text-ink-muted">
                {pos + 1} von {queue.length}
              </span>
              {next ? (
                <Link href={analyseHref(next)} aria-label="Nächstes Foto" className={buttonClass("ghost", navButton)}>
                  <ChevronRight size={16} strokeWidth={1.75} />
                </Link>
              ) : (
                <span aria-hidden className={cn(buttonClass("ghost", navButton), "opacity-40")}>
                  <ChevronRight size={16} strokeWidth={1.75} />
                </span>
              )}
            </>
          )}
        </div>
      </nav>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>

      {/* Stage (left, canvas) and inspector (right, 440 px). At 1440×900 both fit: header 54 + toolbar 44. */}
      <main
        onKeyDown={onKeyDown}
        className="lg:grid lg:h-[calc(100vh-98px)] lg:grid-cols-[minmax(0,1fr)_440px]"
      >
        <section aria-label="Bühne" className="relative bg-canvas lg:min-h-0 lg:overflow-hidden">
          {!error && !record && <p className="py-10 text-center text-ui text-ink-muted">Lade Foto ...</p>}
          {record && (
            <div key={activeStage} className="h-full duration-300 animate-in fade-in">
              {activeStage === "foto" && <PhotoPanel record={record} />}
              {activeStage === "vergleich" && shown && <ArchiveMatch record={record} result={shown} />}
              {activeStage === "karte" && (
                <MapPanel
                  coords={coords ?? null}
                  emptyText={showResult ? "Ort nicht bestimmbar" : "Ort wird bestimmt ..."}
                  startYear={null}
                  photoId={id}
                  zeitreise={false}
                  fill
                />
              )}
            </div>
          )}
        </section>

        <aside aria-label="Erschliessung" className="flex min-h-0 flex-col border-rule/[0.08] bg-paper lg:border-l">
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
            {ended && (
              <div className="space-y-2 rounded border-l-2 border-cert-confirmed bg-paper-2/70 px-3 py-2.5">
                <p className="text-base">
                  {progress.reviewed === progress.total
                    ? `Alle ${progress.total} Prio-1-Fotos geprüft`
                    : `Ende der Liste · ${progress.total - progress.reviewed} noch offen`}
                  {` · ${progress.confirmed} bestätigt · ${progress.corrected} korrigiert · ${skippedCount} übersprungen`}
                </p>
                <a href={exportXlsxUrl({ split: "challenge", priority: 1 })} download className={buttonClass("primary")}>
                  Excel herunterladen
                </a>
              </div>
            )}
            {error && <p className="text-ui text-bad">{error}</p>}

            {missing && (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-ui text-ink-muted">Noch kein Ergebnis für dieses Foto</p>
                {canRunLive && <StartButton onClick={() => startLive(false)}>Analyse starten</StartButton>}
              </div>
            )}

            {failure && (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-ui text-bad">{failure}</p>
                {canRunLive && <StartButton onClick={() => startLive(true)}>Erneut versuchen</StartButton>}
              </div>
            )}

            {/* While it runs, the steps are open at the top; the fields fade in when it ends. */}
            {running && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-ui text-ink-muted">Ort wird bestimmt ...</p>
                  {replaying && (
                    <button type="button" onClick={skipReplay} className={buttonClass("ghost")}>
                      Überspringen
                    </button>
                  )}
                </div>
                <TraceLog items={steps} running />
              </div>
            )}

            {showResult && <ResultPanel result={shown} edit={editState} />}
            {showResult && <SeriesStrip record={record!} />}

            {!running && steps.length > 0 && (
              <div className="relative">
                <TraceLog items={steps} running={false} defaultOpen={false} />
                <div className="absolute right-0 top-0 flex gap-1">
                  {canReplay && (
                    <button type="button" onClick={() => result && startReplay(result)} className={buttonClass("ghost", "h-6 text-meta")}>
                      Erneut abspielen
                    </button>
                  )}
                  {canRunLive && showResult && (
                    <button type="button" onClick={() => startLive(true)} className={buttonClass("ghost", "h-6 text-meta")}>
                      Neu analysieren
                    </button>
                  )}
                </div>
              </div>
            )}

            {showResult && (
              <details className="group">
                <summary className="cursor-pointer list-none text-meta font-medium uppercase tracking-[0.06em] text-ink-muted hover:text-ink">
                  Excel-Zeile <span className="normal-case tracking-normal">▸</span>
                </summary>
                <div className="mt-2">
                  <ExcelRow record={record!} result={shown} heading={false} />
                </div>
              </details>
            )}
          </div>

          {showResult && (
            // Sticky review footer: always in view at 1440×900; on the phone it sticks to the bottom.
            <div className="sticky bottom-0 z-10 border-t border-rule/[0.08] bg-paper/90 px-4 py-3 backdrop-blur">
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
        </aside>
      </main>
    </>
  );
}

function StartButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={buttonClass("secondary")}>
      {children}
    </button>
  );
}
