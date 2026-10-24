"use client";

// Live view of a one-photo batch (Timo, 24.10., the demo moment). The desk's map fills the page; the
// floating panel shows the uploaded photo under a scan bar and the agent's steps as they come in. When the
// result is there, the panel turns into the desk's PhotoDetail and the map flies to the place with the
// desk's flight (rise, dive, sight lines to the named mountains and waters, pin).
// Steps that arrive in a burst (a cached result: the same photo was analysed before) are paced, so the
// replay looks the same as a real run. Zurück shows the steps again; "Ergebnis anzeigen" flies again.
import { Loader2, Upload } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import TraceLog from "@/components/analyse/TraceLog";
import PhotoDetail from "@/components/desk/PhotoDetail";
import { OPEN_UPLOAD } from "@/components/upload/QuickUpload";
import { buttonClass, FOCUS_RING } from "@/components/ui/button";
import Segmented from "@/components/ui/Segmented";
import { errorText, getPhoto, getResult, getTilesUrl, imageUrl, tileTemplate } from "@/lib/api";
import { canRetry, itemTrace, localFile, retry } from "@/lib/batches";
import { cn } from "@/lib/cn";
import { aggregatePlaces, certClass, type DeskItem } from "@/lib/desk";
import { reasoningOf } from "@/lib/reasoning";
import { useReviewStore, withLocalReview } from "@/lib/reviewQueue";
import type { Batch } from "@/lib/types";

const DeskMap = dynamic(() => import("@/components/desk/DeskMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-paper-2" />,
});

/** Pace of shown steps while more are waiting (a burst from the cache); a long backlog goes faster. */
const STEP_MS = 650;
const FAST_STEP_MS = 280;
/** The map has loaded and the photo has been seen before the flight starts. */
const MIN_RUN_MS = 2500;
type Basemap = "karte" | "luftbild";
const BASEMAP_KEY = "desk-basemap"; // shared with the desk

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

export default function LiveDesk({ batch }: { batch: Batch }) {
  useReviewStore(); // a decision in the photo view recolours the dot at once
  const item = batch.items.find((i) => i.status !== "skipped") ?? batch.items[0];
  const trace = itemTrace(batch.id, item.file_name);
  const [shown, setShown] = useState(0);
  const [found, setFound] = useState<DeskItem | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tiles, setTiles] = useState<{ tilesUrl: string; offline: boolean } | null>(null);
  const [basemap, setBasemap] = useState<Basemap>("luftbild");
  const [now, setNow] = useState(() => Date.now());
  const started = useRef(Date.now());
  const localUrl = useObjectUrl(localFile(batch.id, item.file_name));

  useEffect(() => {
    getTilesUrl().then(setTiles);
    try {
      if (localStorage.getItem(BASEMAP_KEY) === "karte") setBasemap("karte");
    } catch {
      // No storage: aerial photo.
    }
    // One viewport, like the desk.
    const html = document.documentElement;
    html.style.scrollbarGutter = "auto";
    return () => {
      html.style.scrollbarGutter = "";
    };
  }, []);

  const failed = item.status === "error";
  const done = item.status === "done" && item.photo_id !== null;
  const drained = shown >= trace.length;
  const working = !failed && !(done && drained && found);

  // Seconds counter while it works.
  useEffect(() => {
    if (!working) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [working]);

  // Show the next waiting step after a pause.
  useEffect(() => {
    if (shown >= trace.length) return;
    const t = setTimeout(() => setShown((s) => s + 1), shown === 0 ? 250 : trace.length - shown > 6 ? FAST_STEP_MS : STEP_MS);
    return () => clearTimeout(t);
  }, [shown, trace.length]);

  // All steps shown and the result is there: load it and fly.
  useEffect(() => {
    if (!done || !drained || found) return;
    let stale = false;
    const wait = Math.max(0, MIN_RUN_MS - (Date.now() - started.current));
    const t = setTimeout(async () => {
      try {
        const id = item.photo_id as string;
        const [record, result] = await Promise.all([getPhoto(id), getResult(id)]);
        if (stale) return;
        setFound({ record, result });
        setOpen(true);
      } catch (e) {
        if (!stale) setError(errorText(e));
      }
    }, wait);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [done, drained, found, item.photo_id]);

  const desk = found ? { record: found.record, result: withLocalReview(found.result) } : null;
  const cls = certClass(desk?.result ?? null);
  const coords = desk?.result?.fields.coordinates?.value;
  const placeKey = desk && coords ? `${cls}:${coords.lat},${coords.lon},${coords.radius_m}` : "";
  const { places, placeOf } = useMemo(() => aggregatePlaces(desk ? [desk] : []), [placeKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const selectedPlace = open && desk ? (placeOf.get(desk.record.id) ?? null) : null;
  const reasoning = useMemo(() => (found ? reasoningOf(found.result) : null), [found]);

  const pickBasemap = (b: Basemap) => {
    setBasemap(b);
    try {
      localStorage.setItem(BASEMAP_KEY, b);
    } catch {
      // Not remembered, still switched.
    }
  };

  const seconds = Math.max(0, Math.round((now - started.current) / 1000));
  const status = failed
    ? null
    : item.status === "queued"
      ? "Wartet auf einen freien Platz ..."
      : item.status === "uploading"
        ? "Foto wird hochgeladen ..."
        : !done || !drained
          ? `Ort wird bestimmt ... ${seconds} s`
          : !found
            ? "Ort gefunden, die Karte fliegt hin ..."
            : coords
              ? null
              : "Kein Ort bestimmbar.";
  const src = localUrl ?? (item.photo_id ? imageUrl(item.photo_id, 960) : null);
  const fileName = item.file_name.slice(item.file_name.lastIndexOf("/") + 1);

  return (
    <main className="relative flex flex-col lg:block lg:h-[calc(100vh-54px)] lg:overflow-hidden">
      <div className="relative order-2 h-[60vh] lg:absolute lg:inset-0 lg:h-auto">
        <div className="absolute inset-0 bg-canvas">
          {tiles && (
            <DeskMap
              places={places}
              tiles={tileTemplate(tiles.tilesUrl, tiles.offline ? "ch.swisstopo.pixelkarte-grau" : "ch.swisstopo.pixelkarte-farbe", "current")}
              grey={tiles.offline}
              aerialTiles={tileTemplate(tiles.tilesUrl, "ch.swisstopo.swissimage", "current")}
              basemap={basemap}
              offline={tiles.offline}
              hoveredPlace={null}
              selectedPlace={selectedPlace}
              onHover={() => {}}
              onPickPhoto={() => setOpen(true)}
              labelOf={() => fileName}
              panelWide={open}
              reasoning={reasoning}
            />
          )}
        </div>
        <Segmented
          label="Hintergrund"
          value={basemap}
          onChange={pickBasemap}
          options={[
            { key: "luftbild", label: "Luftbild" },
            { key: "karte", label: "Karte" },
          ]}
          className="absolute right-12 top-2.5 z-10 border border-rule/[0.08] bg-paper-2/90 shadow-panel backdrop-blur"
        />
      </div>

      <div
        className={cn(
          "order-1 flex flex-col bg-paper lg:absolute lg:bottom-3 lg:left-3 lg:top-3 lg:z-10 lg:overflow-hidden lg:rounded-lg lg:border lg:border-rule/[0.08] lg:shadow-panel",
          "lg:transition-[width] lg:duration-500 lg:ease-[cubic-bezier(0.2,0.7,0.2,1)]",
          open && desk ? "lg:w-[480px]" : "lg:w-[400px]",
        )}
      >
        {open && desk ? (
          <PhotoDetail key={desk.record.id} item={desk} onBack={() => setOpen(false)} />
        ) : (
          <>
            <div className="flex items-center gap-2 border-b border-rule/[0.08] px-3 py-2.5">
              <span className="text-meta font-medium uppercase tracking-[0.06em] text-ink-muted">Live-Analyse</span>
              <span className="ml-auto truncate font-mono text-meta text-ink-muted" title={item.file_name}>
                {fileName}
              </span>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className={cn("relative bg-paper-2", working && "scan")}>
                {src && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={src} alt={`Foto ${fileName}`} className="block max-h-[46vh] w-full object-contain" />
                )}
              </div>

              <div className="px-3 py-3">
                {status && (
                  <p className="flex items-center gap-2 text-ui tnum text-ink" aria-live="polite">
                    {working && <Loader2 size={14} strokeWidth={2} aria-hidden className="animate-spin text-accent" />}
                    {status}
                  </p>
                )}
                {(failed || error) && <p className="text-ui text-bad">{item.error ?? error}</p>}
                {failed && canRetry(batch, item) && (
                  <button type="button" onClick={() => retry(batch.id, item.file_name)} className={buttonClass("secondary", "mt-2")}>
                    Erneut versuchen
                  </button>
                )}
                {shown > 0 && (
                  <div className="mt-4">
                    <TraceLog items={trace.slice(0, shown)} running={working} />
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-wrap gap-2 border-t border-rule/[0.08] p-2">
              {desk && (
                <button type="button" onClick={() => setOpen(true)} className={buttonClass("primary", "flex-1")}>
                  Ergebnis anzeigen
                </button>
              )}
              <button type="button" onClick={() => window.dispatchEvent(new Event(OPEN_UPLOAD))} className={buttonClass("secondary", "flex-1")}>
                <Upload size={14} strokeWidth={1.75} aria-hidden />
                Weiteres Foto
              </button>
              <Link href="/" className={cn(buttonClass("ghost"), FOCUS_RING)}>
                Alle Stapel
              </Link>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
