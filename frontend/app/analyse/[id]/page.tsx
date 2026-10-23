"use client";

// Foto (FRONTPAGE_PLAN 5): breadcrumb with Vorheriges / Nächstes, photo | Erschliessung, then the trace
// ("So entsteht das Ergebnis") and the compact map. The Zeitreise map is not shown here in v3.
// Mock and demo mode replay the cached trace (step 5). Live mode shows a cached result at once and
// streams a new analysis over SSE when asked (step 8); it never starts one on its own (costs money).
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import MapPanel from "@/components/analyse/MapPanel";
import PhotoPanel from "@/components/analyse/PhotoPanel";
import ResultPanel from "@/components/analyse/ResultPanel";
import TraceLog from "@/components/analyse/TraceLog";
import {
  ApiError,
  MODE,
  errorText,
  followAnalysis,
  getDemo,
  getPhoto,
  getResult,
  listChallenge,
  replayTrace,
  startAnalysis,
} from "@/lib/api";
import { analyseHref } from "@/lib/format";
import type { AnalysisResult, PhotoRecord, TraceItem } from "@/lib/types";

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
      .then((ids) => !stale && setQueue(ids))
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

    Promise.all([getPhoto(id), getResult(id)])
      .then(([rec, res]) => {
        if (stale) return;
        setRecord(rec);
        if (!res) {
          setMissing(true);
          return;
        }
        setResult(res);
        if (MODE !== "live" && res.trace?.length) startReplay(res);
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

  const showResult = result && !replaying && !analysing;
  const running = replaying || analysing;
  const canRunLive = MODE === "live" && record && !analysing;
  // Nothing of the result shows before the replay ends, the map included.
  const coords = showResult ? result.fields.coordinates?.value : null;
  const canReplay = MODE !== "live" && showResult && result.trace?.length > 0;
  const pos = queue.indexOf(id);
  const prev = pos > 0 ? queue[pos - 1] : undefined;
  const next = pos >= 0 ? queue[pos + 1] : undefined;
  const signature = record?.signature ?? id;

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
      </nav>

      <main className="wrapper py-6">
        {error && <p className="text-bad">{error}</p>}
        {!error && !record && <p className="text-ink-muted">Lade Foto ...</p>}

        {record && (
          <>
            <div className="grid gap-10 lg:grid-cols-2">
              <PhotoPanel record={record} />

              <div className="space-y-6">
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

                {showResult && <ResultPanel result={result} />}
              </div>
            </div>

            {!running && steps.length > 0 && (
              <section className="relative mt-10 border-t border-rule pt-4">
                <div className="absolute right-0 top-4 flex gap-4 text-small text-ink-muted">
                  {canReplay && (
                    <button type="button" onClick={() => startReplay(result)} className="hover:text-ink-strong">
                      Erneut abspielen
                    </button>
                  )}
                  {canRunLive && showResult && (
                    <button type="button" onClick={() => startLive(true)} className="hover:text-ink-strong">
                      Neu analysieren
                    </button>
                  )}
                </div>
                <TraceLog items={steps} running={false} />
              </section>
            )}

            {showResult && (
              <section className="mt-10 border-t border-rule pt-4">
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
              </section>
            )}
          </>
        )}
      </main>
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
