"use client";

// One file of a batch (UPLOAD_PLAN step 3): thumbnail, state and one line of result. The tile shows the
// picked file at once (object URL) and colours in as the analysis goes: grey while waiting, a spinner while
// running, then the certainty class of the desk (cert-dot), or the error with Erneut versuchen.
import { FileX2, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { buttonClass, FOCUS_RING } from "@/components/ui/button";
import { imageUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { CertClass } from "@/lib/desk";
import { analyseHref, isEmptyValue } from "@/lib/format";
import { effectiveValue, formatValue } from "@/lib/review";
import type { AnalysisResult, BatchItem } from "@/lib/types";

/** What a tile shows: the item status, or for a done item the class of its result ("loading" until it is here). */
export type TileKey = "queued" | "uploading" | "running" | "loading" | CertClass | "error" | "skipped";

export const TILE_LABELS: Record<TileKey, string> = {
  queued: "wartet",
  uploading: "lädt hoch",
  running: "läuft",
  loading: "fertig",
  confirmed: "geprüft",
  sure: "sicher",
  check: "Prüfung nötig",
  open: "nicht bestimmbar",
  error: "Fehler",
  skipped: "übersprungen",
};

const CERT: TileKey[] = ["confirmed", "sure", "check", "open"];

function useObjectUrl(blob: Blob | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return setUrl(null);
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return url;
}

/** Ortschaft (else Gemeinde) and the first building: what the archivist reads first. */
function resultLine(result: AnalysisResult): string {
  const place = effectiveValue(result, "locality") ?? effectiveValue(result, "municipality");
  const buildings = effectiveValue(result, "buildings");
  const building = Array.isArray(buildings) ? buildings[0] : buildings;
  return [formatValue(place), ...(isEmptyValue(building) ? [] : [formatValue(building ?? null)])].join(" · ");
}

interface Props {
  item: BatchItem;
  tile: TileKey;
  result: AnalysisResult | null;
  /** The picked file while it is in memory; else the backend's image once there is a photo id. */
  local: Blob | null;
  canRetry: boolean;
  onRetry: () => void;
}

export default function BatchTile({ item, tile, result, local, canRetry, onRetry }: Props) {
  const localUrl = useObjectUrl(local);
  const src = localUrl ?? (item.photo_id ? imageUrl(item.photo_id, 400) : null);
  const waiting = tile === "queued" || tile === "uploading";
  const busy = tile === "uploading" || tile === "running";
  const done = item.status === "done" && item.photo_id;

  const body = (
    <>
      <div className="relative aspect-[4/3] overflow-hidden rounded-sm bg-paper-2">
        {tile === "skipped" ? (
          <FileX2 size={22} strokeWidth={1.5} aria-hidden className="absolute inset-0 m-auto text-ink-muted" />
        ) : (
          src && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt=""
              loading="lazy"
              className={cn(
                "h-full w-full object-cover transition-[opacity,filter] duration-fade",
                waiting && "opacity-40 grayscale",
                tile === "running" && "opacity-70",
                tile === "error" && "opacity-50 grayscale",
              )}
            />
          )
        )}
        {busy && (
          <span className="absolute right-1.5 top-1.5 rounded-sm bg-paper/90 p-1">
            <Loader2 size={12} strokeWidth={2} aria-hidden className="animate-spin text-ink" />
          </span>
        )}
      </div>
      <div className="mt-1.5 flex min-w-0 items-center gap-1.5">
        {CERT.includes(tile) && <span className={`cert-dot cert-dot-${tile}`} aria-hidden />}
        <span
          className={cn(
            "text-meta font-medium",
            tile === "error" ? "text-bad" : tile === "check" ? "text-warn" : waiting || tile === "skipped" ? "text-ink-muted" : "text-ink",
          )}
        >
          {TILE_LABELS[tile]}
        </span>
      </div>
      <p className="mt-0.5 truncate font-mono text-micro text-ink-muted" title={item.file_name}>
        {item.file_name}
      </p>
      {result && <p className="mt-0.5 truncate text-meta text-ink">{resultLine(result)}</p>}
      {item.error && <p className="mt-0.5 line-clamp-2 text-meta text-ink-muted">{item.error}</p>}
    </>
  );

  return (
    <div className="min-w-0">
      {done ? (
        <Link
          href={analyseHref(item.photo_id as string)}
          className={cn("group block rounded-sm transition-opacity duration-hover hover:opacity-90", FOCUS_RING)}
        >
          {body}
        </Link>
      ) : (
        body
      )}
      {canRetry && (
        <button type="button" onClick={onRetry} className={buttonClass("ghost", "-ml-2 mt-1 h-7")}>
          Erneut versuchen
        </button>
      )}
    </div>
  );
}
