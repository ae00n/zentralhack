"use client";

// One uploaded batch (UPLOAD_PLAN step 2, first version): name, progress, and the files as a list with
// status, error and Erneut versuchen. Step 3 turns the list into the thumbnail grid, step 4 adds the desk.
import { ArrowLeft, Download } from "lucide-react";
import Link from "next/link";
import { buttonClass, FOCUS_RING } from "@/components/ui/button";
import { MODE } from "@/lib/api";
import { batchCounts, batchExportUrl, canRetry, estimate, getBatch, isRunning, retry, useBatches } from "@/lib/batches";
import { cn } from "@/lib/cn";
import { analyseHref } from "@/lib/format";
import { BATCH_STATUS_LABELS } from "@/lib/labels";
import type { BatchItemStatus } from "@/lib/types";

const STATUS_TONE: Record<BatchItemStatus, string> = {
  queued: "text-ink-muted",
  uploading: "text-ink",
  running: "text-ink",
  done: "text-ink",
  error: "text-bad",
  skipped: "text-ink-muted",
};

export default function BatchView({ id }: { id: string }) {
  const { ready } = useBatches();
  const batch = getBatch(id);

  if (!batch) {
    return (
      <main className="mx-auto w-full max-w-[960px] px-4 py-10">
        <p className="text-ui text-ink-muted">
          {!ready
            ? "Lade Stapel ..."
            : MODE === "mock"
              ? "Stapel nicht gefunden. In den Beispieldaten gehen Stapel beim Neuladen verloren."
              : "Stapel nicht gefunden."}
        </p>
        {ready && (
          <Link href="/" className={buttonClass("secondary", "mt-4")}>
            Zur Übersicht
          </Link>
        )}
      </main>
    );
  }

  const c = batchCounts(batch);
  const work = c.total - c.skipped;
  const finished = c.done + c.error;
  const running = isRunning(batch);
  const left = estimate(c.queued + c.uploading + c.running);
  const retryable = batch.items.filter((i) => canRetry(batch, i)).length;

  return (
    <main className="mx-auto w-full max-w-[960px] px-4 py-6 sm:py-8">
      <Link href="/" className={cn("-ml-1 inline-flex items-center gap-1.5 rounded px-1 py-0.5 text-ui text-ink-muted hover:text-ink", FOCUS_RING)}>
        <ArrowLeft className="size-4" aria-hidden />
        Alle Stapel
      </Link>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-h1 text-ink-strong">{batch.name}</h1>
          <p className="mt-1 text-ui tnum text-ink-muted" aria-live="polite">
            {finished} von {work} analysiert
            {running && ` · noch ca. ${left.minutes} Min.`}
            {c.error > 0 && ` · ${c.error} Fehler`}
            {c.skipped > 0 && ` · ${c.skipped} übersprungen`}
            {MODE !== "mock" && !!batch.cost_usd && ` · ${batch.cost_usd.toFixed(2)} USD`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {retryable > 0 && (
            <button type="button" onClick={() => retry(batch.id)} className={buttonClass("secondary")}>
              {retryable === 1 ? "Fehler erneut versuchen" : `${retryable} Fehler erneut versuchen`}
            </button>
          )}
          {c.done > 0 && (
            <a href={batchExportUrl(batch)} download className={buttonClass("primary")}>
              <Download size={14} strokeWidth={1.75} aria-hidden />
              Excel herunterladen
            </a>
          )}
        </div>
      </div>
      <div className="mt-3 h-1 w-full overflow-hidden rounded-sm bg-paper-2" aria-hidden>
        <div className="h-full bg-ink/60 transition-[width] duration-fade" style={{ width: `${work ? (finished / work) * 100 : 0}%` }} />
      </div>
      {running && batch.runner === "client" && (
        <p className="mt-2 text-meta text-ink-muted">Dieses Fenster bitte offen lassen, bis die Analyse fertig ist.</p>
      )}

      <ul className="mt-5 divide-y divide-rule/[0.06] border-y border-rule/[0.06]">
        {batch.items.map((i) => (
          <li key={i.file_name} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
            <span className={cn("w-24 shrink-0 text-meta font-medium", STATUS_TONE[i.status])}>{BATCH_STATUS_LABELS[i.status]}</span>
            <span className="min-w-0 flex-1 truncate font-mono text-meta text-ink" title={i.file_name}>
              {i.file_name}
            </span>
            {i.error && <span className="w-full pl-[108px] text-meta text-ink-muted sm:w-auto sm:pl-0">{i.error}</span>}
            {i.status === "done" && i.photo_id && (
              <Link href={analyseHref(i.photo_id)} className={buttonClass("ghost", "h-7")}>
                Öffnen
              </Link>
            )}
            {canRetry(batch, i) && (
              <button type="button" onClick={() => retry(batch.id, i.file_name)} className={buttonClass("ghost", "h-7")}>
                Erneut versuchen
              </button>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
