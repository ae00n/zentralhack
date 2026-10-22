"use client";

// Analyse / "Ort & Zeit" (build step 3). Layout follows the team mock (question 2.1, 2.10):
// left = map + Zeitreise (steps 4 and 9), right = photo, result, trace.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import PhotoPanel from "@/components/analyse/PhotoPanel";
import ResultPanel from "@/components/analyse/ResultPanel";
import TraceLog from "@/components/analyse/TraceLog";
import { ApiError, MODE, getPhoto, getResult, replayTrace } from "@/lib/api";
import { formatCoordinates } from "@/lib/format";
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
  const cancelReplay = useRef<(() => void) | undefined>(undefined);

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
        // Mock and demo mode replay the cached trace so it looks live; live mode streams (step 8).
        if (MODE !== "live" && res.trace?.length) {
          setReplaying(true);
          cancelReplay.current = replayTrace(
            res.trace,
            (item) => setSteps((prev) => [...prev, item]),
            () => setReplaying(false),
          );
        } else {
          setSteps(res.trace ?? []);
        }
      })
      .catch((e: unknown) =>
        !stale &&
        setError(
          e instanceof ApiError && e.status === 404
            ? "Dieses Foto gibt es nicht."
            : `Foto konnte nicht geladen werden (${e instanceof Error ? e.message : String(e)}).`,
        ),
      );

    return () => {
      stale = true;
      cancelReplay.current?.();
    };
  }, [id]);

  const skipReplay = () => {
    if (!result) return;
    cancelReplay.current?.();
    setSteps(result.trace ?? []);
    setReplaying(false);
  };

  const showResult = result && !replaying;
  // Nothing of the result shows before the replay ends, the map included.
  const coords = showResult ? result.fields.coordinates?.value : null;

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-6 md:px-8">
      <Link href="/" className="text-meta text-ink-muted hover:text-accent">
        ← Archiv
      </Link>

      {error && <p className="mt-6 text-bad">{error}</p>}
      {!error && !record && <p className="mt-6 text-ink-muted">Lade Foto ...</p>}

      {record && (
        <div className="mt-4 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,520px)]">
          <div className="order-2 lg:order-1">
            <section className="flex aspect-[4/3] flex-col items-center justify-center bg-paper-2 text-center">
              <p className="font-serif text-section">Karte</p>
              <p className="mt-1 font-mono text-meta text-ink-muted">
                {coords ? formatCoordinates(coords) : showResult ? "Keine Koordinaten" : "Ort wird bestimmt ..."}
              </p>
            </section>
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
