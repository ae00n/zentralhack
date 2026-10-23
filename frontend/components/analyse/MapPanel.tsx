"use client";

// Map panel of the Analyse screen (build step 4): today's SWISSIMAGE with the pin and the
// uncertainty circle. Step 9 puts the Zeitreise layer and slider here.
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { getTilesUrl, tileTemplate } from "@/lib/api";
import { formatCoordinates } from "@/lib/format";
import type { Coordinates } from "@/lib/types";

const MapView = dynamic(() => import("@/components/map/MapView"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-paper-2" />,
});

interface Props {
  /** null while the replay runs or when the result has no coordinates. */
  coords: Coordinates | null;
  /** Text in the empty panel when there are no coordinates. */
  emptyText: string;
}

export default function MapPanel({ coords, emptyText }: Props) {
  const [tiles, setTiles] = useState<{ tilesUrl: string; offline: boolean } | null>(null);

  useEffect(() => {
    let stale = false;
    getTilesUrl().then((t) => !stale && setTiles(t));
    return () => {
      stale = true;
    };
  }, []);

  return (
    <section>
      <div className="relative aspect-[4/3] bg-paper-2">
        {coords && tiles ? (
          <div className="fade-in absolute inset-0">
            <MapView
              center={coords}
              tiles={tileTemplate(tiles.tilesUrl, "ch.swisstopo.swissimage", "current")}
              layerLabel="SWISSIMAGE"
              offline={tiles.offline}
            />
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <p className="font-serif text-section">Karte</p>
            <p className="mt-1 text-meta text-ink-muted">{emptyText}</p>
          </div>
        )}
      </div>
      {coords && (
        <p className="mt-2 font-mono text-meta text-ink-muted">
          {formatCoordinates(coords)}
          <span className="font-sans"> · Kreis zeigt die Unsicherheit</span>
        </p>
      )}
    </section>
  );
}
