"use client";

// Map panel of the Analyse screen: pin and uncertainty circle (step 4) on a base layer that follows
// the Zeitreise slider (step 9): zeitreihen at the snapped map year, SWISSIMAGE for "heute".
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { getPhoto, getTilesUrl, getTimeline, tileTemplate } from "@/lib/api";
import { formatCoordinates } from "@/lib/format";
import { THIS_YEAR, clampYear, datedPhotos, nearestPhoto, snapToMap } from "@/lib/timeline";
import type { Coordinates, Timeline } from "@/lib/types";
import Zeitreise, { type StripPhoto } from "./Zeitreise";

const MapView = dynamic(() => import("@/components/map/MapView"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-paper-2" />,
});

// zeitreihen tiles past z16 are empty or blank on swisstopo; MapLibre scales z16 up instead.
const ZEITREIHEN_MAX_ZOOM = 16;
// Records for captions and credits; a timeline set is rarely larger.
const MAX_STRIP = 40;

interface Props {
  /** null while the replay runs or when the result has no coordinates. */
  coords: Coordinates | null;
  /** Text in the empty panel when there are no coordinates. */
  emptyText: string;
  /** Where the slider starts: the analysis' year estimate; null = today. */
  startYear: number | null;
  /** The photo under analysis. */
  photoId: string;
  /**
   * false = the compact v3 detail map (240px, SWISSIMAGE, no slider). The challenge photos are from
   * 2003 to 2013, so the Zeitreise is optional there (CHALLENGE_BRIEF 5).
   */
  zeitreise?: boolean;
  /** Fill the parent (the detail page stage tab) instead of a fixed height. */
  fill?: boolean;
}

export default function MapPanel({ coords, emptyText, startYear, photoId, zeitreise = true, fill = false }: Props) {
  const [tiles, setTiles] = useState<{ tilesUrl: string; offline: boolean } | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [photos, setPhotos] = useState<StripPhoto[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [year, setYear] = useState(clampYear(startYear ?? THIS_YEAR));
  // The year the map shows lags the slider a little, so dragging does not request every sheet on the way.
  const [mapYear, setMapYear] = useState(year);

  useEffect(() => {
    let stale = false;
    getTilesUrl().then((t) => !stale && setTiles(t));
    return () => {
      stale = true;
    };
  }, []);

  useEffect(() => {
    setYear(clampYear(startYear ?? THIS_YEAR));
  }, [startYear]);

  useEffect(() => {
    const t = setTimeout(() => setMapYear(year), 150);
    return () => clearTimeout(t);
  }, [year]);

  useEffect(() => {
    if (!coords || !zeitreise) return;
    let stale = false;
    setStatus("loading");
    getTimeline(coords.lat, coords.lon)
      .then(async (tl) => {
        if (stale) return;
        setTimeline(tl);
        const dated = datedPhotos(tl.photos).slice(0, MAX_STRIP);
        setPhotos(dated.map((p) => ({ ...p, record: null })));
        setStatus("ready");
        // Captions and credits come from the records; the strip shows ids until they arrive.
        const records = await Promise.all(dated.map((p) => getPhoto(p.id).catch(() => null)));
        if (!stale) setPhotos(dated.map((p, i) => ({ ...p, record: records[i] })));
      })
      .catch(() => !stale && setStatus("error"));
    return () => {
      stale = true;
    };
  }, [coords?.lat, coords?.lon, zeitreise]); // eslint-disable-line react-hooks/exhaustive-deps

  const mapYears = useMemo(() => timeline?.map_years ?? [], [timeline]);
  // Without map_years there is no valid TIME to ask for, so the map stays on SWISSIMAGE.
  const mapTime = zeitreise ? snapToMap(mapYear, mapYears) : ({ kind: "heute" } as const);
  const nearest = nearestPhoto(photos, year);

  const layer =
    mapTime.kind === "heute"
      ? { tiles: "ch.swisstopo.swissimage" as const, time: "current", maxZoom: 19, label: "SWISSIMAGE" }
      : {
          tiles: "ch.swisstopo.zeitreihen" as const,
          time: String(mapTime.time),
          maxZoom: ZEITREIHEN_MAX_ZOOM,
          label: `Zeitreise ${mapTime.year}`,
        };

  return (
    <section className={fill ? "flex h-full flex-col p-4" : undefined}>
      <div className={`relative bg-paper-2 ${fill ? "min-h-[50vh] flex-1 lg:min-h-0" : zeitreise ? "aspect-[4/3]" : "h-60"}`}>
        {coords && tiles ? (
          <div className="fade-in absolute inset-0">
            <MapView
              center={coords}
              tiles={tileTemplate(tiles.tilesUrl, layer.tiles, layer.time)}
              tilesMaxZoom={layer.maxZoom}
              layerLabel={layer.label}
              offline={tiles.offline}
            />
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <p className="text-h3">Karte</p>
            <p className="mt-1 text-meta text-ink-muted">{emptyText}</p>
          </div>
        )}
      </div>
      {coords && (
        <>
          <p className="mt-2 font-mono text-meta text-ink-muted">
            {formatCoordinates(coords)}
            <span className="font-sans"> · Kreis zeigt die Unsicherheit</span>
          </p>
          {zeitreise && (
          <Zeitreise
            year={year}
            onYear={setYear}
            mapTime={snapToMap(year, mapYears)}
            mapYears={mapYears}
            photos={photos}
            nearest={nearest}
            currentId={photoId}
            status={status}
          />
          )}
        </>
      )}
    </section>
  );
}
