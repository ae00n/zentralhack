"use client";

// The place today, at street level (Said, 24.10.): once the map flight has landed on a picked photo, a pane
// splits off on the right with Google Street View at the found spot, looking towards the main landmark of
// the reasoning when there is one. Keyless Google embed (the one maps.google.com hands out for
// "output=svembed"); only the coordinates go to Google, never the photo.
import { useEffect, useState } from "react";
import { ArrowUpRight, X } from "lucide-react";
import { FOCUS_RING } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { Reasoning } from "@/lib/reasoning";

interface Props {
  lat: number;
  lon: number;
  signature: string;
  reasoning: Promise<Reasoning | null> | null;
  width: number;
  onClose: () => void;
}

/** Compass bearing in degrees from a to b. */
function bearing(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const k = Math.PI / 180;
  const y = Math.sin((b.lon - a.lon) * k) * Math.cos(b.lat * k);
  const x = Math.cos(a.lat * k) * Math.sin(b.lat * k) - Math.sin(a.lat * k) * Math.cos(b.lat * k) * Math.cos((b.lon - a.lon) * k);
  return (Math.atan2(y, x) / k + 360) % 360;
}

const embedUrl = (lat: number, lon: number, heading: number) =>
  `https://www.google.com/maps/embed?origin=mfe&pb=!6m7!1m6!2m2!1d${lat}!2d${lon}!3f${heading.toFixed(0)}!4f0!5f1`;
const mapsUrl = (lat: number, lon: number, heading: number) =>
  `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}&heading=${heading.toFixed(0)}`;

const coord = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(5)}° ${v >= 0 ? pos : neg}`;

export default function StreetPane({ lat, lon, signature, reasoning, width, onClose }: Props) {
  const [view, setView] = useState<{ heading: number; toward: string | null } | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let live = true;
    (reasoning ?? Promise.resolve(null))
      .catch(() => null)
      .then((why) => {
        if (!live) return;
        const l = why?.landmarks.find((x) => x.kind === "mountain") ?? why?.landmarks[0];
        setView(l ? { heading: bearing({ lat, lon }, l), toward: l.name } : { heading: 0, toward: null });
      });
    return () => {
      live = false;
    };
  }, [lat, lon, reasoning]);

  return (
    <aside
      aria-label="Strassenansicht"
      className="street-pane absolute bottom-3 right-3 top-3 z-20 hidden flex-col overflow-hidden rounded-lg lg:flex"
      style={{ width }}
    >
      <header className="flex items-start gap-3 border-b border-white/10 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-mono text-micro uppercase tracking-[0.14em] text-white/55">
            <span className="street-live" aria-hidden />
            Strassenansicht heute · {signature}
          </p>
          <p className="mt-0.5 truncate font-mono text-ui tnum text-white">
            {coord(lat, "N", "S")}&nbsp;&nbsp;{coord(lon, "O", "W")}
          </p>
          <p className="truncate font-mono text-micro tnum text-white/55">
            {view ? `Blick ${view.heading.toFixed(0).padStart(3, "0")}°${view.toward ? ` · Richtung ${view.toward}` : ""}` : "Blickrichtung ..."}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Strassenansicht schliessen"
          className={cn("rounded p-1 text-white/70 transition-colors duration-hover hover:bg-white/10 hover:text-white", FOCUS_RING)}
        >
          <X className="size-4" aria-hidden />
        </button>
      </header>

      <div className="relative min-h-0 flex-1 bg-black">
        {view && (
          <iframe
            key={`${lat},${lon},${view.heading.toFixed(0)}`}
            title={`Google Street View bei ${signature}`}
            src={embedUrl(lat, lon, view.heading)}
            onLoad={() => setLoaded(true)}
            className={cn("absolute inset-0 h-full w-full border-0 transition-opacity duration-700", loaded ? "opacity-100" : "opacity-0")}
            loading="eager"
            referrerPolicy="no-referrer-when-downgrade"
            allowFullScreen
          />
        )}
        {/* Targeting frame: corner brackets and a small reticle, never in the way of the mouse. */}
        <div aria-hidden className="street-frame pointer-events-none absolute inset-0">
          <i /><i /><i /><i />
          <b />
        </div>
        {!loaded && (
          <div className="street-scan pointer-events-none absolute inset-0 flex items-end p-3">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-white/60">Panorama wird geladen ...</span>
          </div>
        )}
      </div>

      <footer className="flex items-center gap-2 border-t border-white/10 px-3 py-1.5 font-mono text-micro text-white/55">
        <span className="truncate">Google Street View, nächstes Panorama zum Standort</span>
        {view && (
          <a
            href={mapsUrl(lat, lon, view.heading)}
            target="_blank"
            rel="noreferrer"
            className={cn("ml-auto inline-flex shrink-0 items-center gap-1 rounded-sm text-white/80 hover:text-white", FOCUS_RING)}
          >
            In Google Maps öffnen
            <ArrowUpRight className="size-3.5" aria-hidden />
          </a>
        )}
      </footer>
    </aside>
  );
}
