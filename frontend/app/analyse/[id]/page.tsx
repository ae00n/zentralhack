"use client";

// Analyse / "Ort & Zeit" (build step 3). Layout follows the team mock (question 2.1, 2.10):
// left = map (step 4) + Zeitreise (step 9), right = photo, result, trace.
// Mock and demo mode replay the cached trace (step 5). Live mode shows a cached result at once and
// streams a new analysis over SSE when asked (step 8); it never starts one on its own (costs money).
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
  replayTrace,
  startAnalysis,
} from "@/lib/api";
import { analyseHref } from "@/lib/format";
import { estimatedYear } from "@/lib/timeline";
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
  const [demoIds, setDemoIds] = useState<string[]>([]);
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

  // Pitch order, for the "Nächste Karte" link.
  useEffect(() => {
    getDemo()
      .then((items) => setDemoIds(items.map((d) => d.id)))
      .catch(() => setDemoIds([]));
  }, []);

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
  const canRunLive = MODE === "live" && record && !analysing;
  // Nothing of the result shows before the replay ends, the map included.
  const coords = showResult ? result.fields.coordinates?.value : null;
  const canReplay = MODE !== "live" && showResult && result.trace?.length > 0;
  const demoIndex = demoIds.indexOf(id);
  const nextDemo = demoIndex >= 0 ? demoIds[demoIndex + 1] : undefined;

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-6 md:px-8">
      <div className="flex items-baseline justify-between gap-4 text-meta text-ink-muted">
        <Link href="/" className="hover:text-accent">
          ← Archiv
        </Link>
        <div className="flex items-baseline gap-4">
          {canReplay && (
            <button type="button" onClick={() => startReplay(result)} className="hover:text-accent">
              Analyse erneut abspielen
            </button>
          )}
          {canRunLive && showResult && (
            <button type="button" onClick={() => startLive(true)} className="hover:text-accent">
              Neu analysieren
            </button>
          )}
          {nextDemo && (
            <Link href={analyseHref(nextDemo)} className="hover:text-accent">
              Nächste Karte →
            </Link>
          )}
        </div>
      </div>

      {error && <p className="mt-6 text-bad">{error}</p>}
      {!error && !record && <p className="mt-6 text-ink-muted">Lade Foto ...</p>}

      {record && (
        <div className="mt-4 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,520px)]">
          <div className="order-2 lg:order-1">
            <MapPanel
              coords={coords ?? null}
              emptyText={
                showResult ? "Keine Koordinaten" : missing || failure ? "Keine Analyse" : "Ort wird bestimmt ..."
              }
              startYear={showResult ? estimatedYear(result) : null}
              photoId={id}
            />
          </div>

          <div className="order-1 space-y-6 lg:order-2">
            <PhotoPanel record={record} />

            {missing && (
              <div className="flex flex-wrap items-baseline justify-between gap-3 border-y border-rule py-3">
                <p className="text-ink-muted">Für dieses Foto liegt noch keine Analyse vor.</p>
                {canRunLive && <StartButton onClick={() => startLive(false)}>Analyse starten</StartButton>}
              </div>
            )}

            {failure && (
              <div className="flex flex-wrap items-baseline justify-between gap-3 border-y border-rule py-3">
                <p className="text-bad">{failure}</p>
                {canRunLive && <StartButton onClick={() => startLive(true)}>Erneut versuchen</StartButton>}
              </div>
            )}

            {analysing && (
              <p className="border-y border-rule py-3 text-ink-muted">Ort und Zeitraum werden bestimmt ...</p>
            )}

            {result && replaying && (
              <div className="flex items-baseline justify-between border-y border-rule py-3">
                <p className="text-ink-muted">Ort und Zeitraum werden bestimmt ...</p>
                <button type="button" onClick={skipReplay} className="text-meta text-ink-muted hover:text-accent">
                  Überspringen
                </button>
              </div>
            )}
            {showResult && <ResultPanel result={result} />}

            {(steps.length > 0 || analysing) && <TraceLog items={steps} running={replaying || analysing} />}
          </div>
        </div>
      )}
    </main>
  );
}

function StartButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-ink px-3 py-1.5 text-meta hover:border-accent hover:text-accent"
    >
      {children}
    </button>
  );
}
