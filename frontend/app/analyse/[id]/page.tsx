"use client";

// Analyse / "Ort & Zeit" (build step 3). Layout follows the team mock (question 2.1, 2.10):
// left = map (step 4) + Zeitreise (step 9), right = photo, result, trace.
// Mock and demo mode replay the cached trace (step 5); live mode streams it (step 8).
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import MapPanel from "@/components/analyse/MapPanel";
import PhotoPanel from "@/components/analyse/PhotoPanel";
import ResultPanel from "@/components/analyse/ResultPanel";
import TraceLog from "@/components/analyse/TraceLog";
import { ApiError, MODE, errorText, getDemo, getPhoto, getResult, replayTrace } from "@/lib/api";
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
  const [demoIds, setDemoIds] = useState<string[]>([]);
  const cancelReplay = useRef<(() => void) | undefined>(undefined);

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
    };
  }, [id, startReplay]);

  const skipReplay = () => {
    if (!result) return;
    cancelReplay.current?.();
    setSteps(result.trace ?? []);
    setReplaying(false);
  };

  const showResult = result && !replaying;
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
              emptyText={showResult ? "Keine Koordinaten" : missing ? "Keine Analyse" : "Ort wird bestimmt ..."}
            />
          </div>

          <div className="order-1 space-y-6 lg:order-2">
            <PhotoPanel record={record} />

            {missing && <p className="text-ink-muted">Für dieses Foto liegt noch keine Analyse vor.</p>}

            {result && !showResult && (
              <div className="flex items-baseline justify-between border-y border-rule py-3">
                <p className="text-ink-muted">Ort und Zeitraum werden bestimmt ...</p>
                <button type="button" onClick={skipReplay} className="text-meta text-ink-muted hover:text-accent">
                  Überspringen
                </button>
              </div>
            )}
            {showResult && <ResultPanel result={result} />}

            {steps.length > 0 && <TraceLog items={steps} running={replaying} />}
          </div>
        </div>
      )}
    </main>
  );
}
