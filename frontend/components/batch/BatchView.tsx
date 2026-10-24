"use client";

// One uploaded batch (UPLOAD_PLAN step 3): progress, then a grid of tiles that colour in while the analysis
// runs. Chips above the grid count and filter by state (in Arbeit, Prüfung nötig, nicht bestimmbar, sicher,
// geprüft, Fehler, übersprungen). Done photos open in the photo view at once, while the rest still runs.
// Step 4 adds the desk (map, review queue) for the batch.
import { ArrowLeft, Download } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import BatchTile, { TILE_LABELS, type TileKey } from "@/components/batch/BatchTile";
import { buttonClass, FOCUS_RING } from "@/components/ui/button";
import { MODE, listResults } from "@/lib/api";
import {
  batchCounts,
  batchExportUrl,
  batchPhotoIds,
  canRetry,
  estimate,
  getBatch,
  isRunning,
  localFile,
  retry,
  useBatches,
} from "@/lib/batches";
import { cn } from "@/lib/cn";
import { certClass } from "@/lib/desk";
import { useReviewStore, withLocalReview } from "@/lib/reviewQueue";
import type { AnalysisResult, BatchItem } from "@/lib/types";

type Group = "all" | "active" | "check" | "open" | "sure" | "confirmed" | "error" | "skipped";

const GROUPS: { key: Group; label: string; dot?: string }[] = [
  { key: "all", label: "Alle" },
  { key: "active", label: "in Arbeit" },
  { key: "check", label: TILE_LABELS.check, dot: "check" },
  { key: "open", label: TILE_LABELS.open, dot: "open" },
  { key: "sure", label: TILE_LABELS.sure, dot: "sure" },
  { key: "confirmed", label: TILE_LABELS.confirmed, dot: "confirmed" },
  { key: "error", label: TILE_LABELS.error },
  { key: "skipped", label: TILE_LABELS.skipped },
];

function groupOf(tile: TileKey): Group {
  return tile === "queued" || tile === "uploading" || tile === "running" || tile === "loading" ? "active" : tile;
}

function tileOf(item: BatchItem, result: AnalysisResult | null | undefined): TileKey {
  if (item.status !== "done") return item.status;
  return result ? certClass(result) : "loading";
}

export default function BatchView({ id }: { id: string }) {
  const { ready } = useBatches();
  useReviewStore(); // a decision in the photo view recolours its tile at once
  const batch = getBatch(id);
  const [results, setResults] = useState<Map<string, AnalysisResult | null>>(new Map());
  const [group, setGroup] = useState<Group>("all");

  // Results of the done photos; listResults caches, so each new done photo costs one request.
  const doneIds = batch ? batchPhotoIds(batch) : [];
  const doneKey = doneIds.join(",");
  useEffect(() => {
    if (!doneIds.length) return;
    let stale = false;
    listResults(doneIds)
      .then((m) => !stale && setResults(m))
      .catch(() => {
        // The tile stays "fertig" without a class; the photo view still opens.
      });
    return () => {
      stale = true;
    };
  }, [doneKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!batch) {
    return (
      <main className="mx-auto w-full max-w-[1200px] px-4 py-10">
        <p className="text-ui text-ink-muted">
          {!ready
            ? "Lade Stapel ..."
            : MODE === "mock"
              ? "Stapel nicht gefunden. In den Beispieldaten gehen Stapel beim Neuladen verloren."
              : "Stapel nicht gefunden."}
        </p>
        {ready && (
          <Link href="/" className={buttonClass("secondary", "mt-4")}>
            Zur Karte
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

  const tiles = batch.items.map((item) => {
    const result = item.photo_id ? withLocalReview(results.get(item.photo_id) ?? null) : null;
    return { item, result, tile: tileOf(item, result) };
  });
  const counts = new Map<Group, number>([["all", tiles.length]]);
  for (const t of tiles) counts.set(groupOf(t.tile), (counts.get(groupOf(t.tile)) ?? 0) + 1);
  // A filter that ran empty (all errors retried, all checked) falls back to Alle.
  const shownGroup = counts.get(group) ? group : "all";
  const shown = shownGroup === "all" ? tiles : tiles.filter((t) => groupOf(t.tile) === shownGroup);

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:py-8">
      <Link href="/" className={cn("-ml-1 inline-flex items-center gap-1.5 rounded px-1 py-0.5 text-ui text-ink-muted hover:text-ink", FOCUS_RING)}>
        <ArrowLeft className="size-4" aria-hidden />
        Zur Karte
      </Link>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-h1 text-ink-strong">{batch.name}</h1>
          <p className="mt-1 text-ui tnum text-ink-muted" aria-live="polite">
            {running ? `${finished} von ${work} analysiert · noch ca. ${left.minutes} Min.` : `${work} analysiert`}
            {MODE !== "mock" && !!batch.cost_usd && ` · ${batch.cost_usd.toFixed(2)} USD`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {retryable > 1 && (
            <button type="button" onClick={() => retry(batch.id)} className={buttonClass("secondary")}>
              Alle {retryable} Fehler erneut versuchen
            </button>
          )}
          {/* From sm the header carries the Excel button (same pattern as DeskBand). */}
          {c.done > 0 && (
            <a href={batchExportUrl(batch)} download className={buttonClass("primary", "sm:hidden")}>
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
        <p className="mt-2 text-meta text-ink-muted">
          Dieses Fenster bitte offen lassen, bis die Analyse fertig ist. Fertige Fotos lassen sich schon öffnen und prüfen.
        </p>
      )}

      <div role="group" aria-label="Filter" className="mt-5 flex flex-wrap gap-1">
        {GROUPS.filter((g) => g.key === "all" || counts.get(g.key)).map((g) => (
          <button
            key={g.key}
            type="button"
            onClick={() => setGroup(g.key)}
            aria-pressed={shownGroup === g.key}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded px-2 text-ui transition-colors duration-hover",
              FOCUS_RING,
              shownGroup === g.key ? "bg-paper-2 font-medium text-ink" : "text-ink-muted hover:bg-paper-2/60 hover:text-ink",
            )}
          >
            {g.dot && <span className={`cert-dot cert-dot-${g.dot}`} aria-hidden />}
            {g.label}
            <span className="tnum text-ink-muted">{counts.get(g.key)}</span>
          </button>
        ))}
      </div>

      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {shown.map(({ item, result, tile }) => (
          <li key={item.file_name}>
            <BatchTile
              item={item}
              tile={tile}
              result={result}
              local={localFile(batch.id, item.file_name)}
              canRetry={canRetry(batch, item)}
              onRetry={() => retry(batch.id, item.file_name)}
            />
          </li>
        ))}
      </ul>
    </main>
  );
}
