"use client";

// Zeitreise (build step 9): year slider under the map, the archive photo nearest to that year shown
// large, and a strip of all dated photos of this place. The map itself lives in MapPanel.
import Link from "next/link";
import { imageUrl } from "@/lib/api";
import { analyseHref, photoTitle } from "@/lib/format";
import { FIRST_YEAR, THIS_YEAR, type MapTime } from "@/lib/timeline";
import type { PhotoRecord, TimelinePhoto } from "@/lib/types";

export type StripPhoto = TimelinePhoto & { year: number; record: PhotoRecord | null };

interface Props {
  year: number;
  onYear: (year: number) => void;
  mapTime: MapTime;
  /** Valid zeitreihen TIME values, drawn as ticks on the axis. */
  mapYears: number[];
  photos: StripPhoto[];
  nearest: StripPhoto | null;
  /** The photo under analysis; it is not linked to itself. */
  currentId: string;
  status: "loading" | "ready" | "error";
}

const LABEL_YEARS = [1880, 1900, 1920, 1940, 1960, 1980, 2000, 2020];

function pos(year: number): string {
  return `${((year - FIRST_YEAR) / (THIS_YEAR - FIRST_YEAR)) * 100}%`;
}

function caption(p: StripPhoto): string {
  return `${p.year} · ${p.record?.signature ?? p.id}`;
}

export default function Zeitreise({ year, onYear, mapTime, mapYears, photos, nearest, currentId, status }: Props) {
  return (
    <section className="mt-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-h3">Zeitreise</h2>
        <p className="text-meta text-ink-muted">
          <span className="font-mono text-h3 font-normal text-accent">{year}</span>
          {" · "}
          {mapTime.kind === "heute" ? "Heute, Luftbild SWISSIMAGE" : `Karte von ${mapTime.year}`}
        </p>
      </div>

      <input
        type="range"
        min={FIRST_YEAR}
        max={THIS_YEAR}
        step={1}
        value={year}
        onChange={(e) => onYear(Number(e.target.value))}
        aria-label="Jahr"
        aria-valuetext={mapTime.kind === "heute" ? `${year}, heute` : `${year}, Karte von ${mapTime.year}`}
        className="zeitreise-slider mt-3 w-full"
      />

      {/* Axis: a tick per map sheet, photo marks above, mono labels every 20 years. */}
      <div className="relative mx-[7px] h-7" aria-hidden>
        {mapYears.map((t) => (
          <span key={t} className="absolute top-0 h-1.5 w-px bg-rule" style={{ left: pos(Math.floor(t / 10000)) }} />
        ))}
        {photos.map((p) => (
          <span
            key={p.id}
            className={`absolute -top-1 h-1 w-1 ${p === nearest ? "bg-accent" : "bg-ink-muted"}`}
            style={{ left: pos(p.year) }}
          />
        ))}
        {LABEL_YEARS.map((y) => (
          <span
            key={y}
            className="absolute top-2 -translate-x-1/2 font-mono text-meta text-ink-muted"
            style={{ left: pos(y) }}
          >
            {y}
          </span>
        ))}
      </div>

      {status === "loading" && <p className="mt-3 text-meta text-ink-muted">Lade Archivfotos dieses Orts ...</p>}
      {status === "error" && (
        <p className="mt-3 text-meta text-ink-muted">Archivfotos dieses Orts konnten nicht geladen werden.</p>
      )}
      {status === "ready" && photos.length === 0 && (
        <p className="mt-3 text-meta text-ink-muted">Keine datierten Archivfotos in der Nähe. Die Karte zeigt trotzdem jedes Jahr.</p>
      )}

      {nearest && (
        <div className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,280px)_1fr]">
          <div className="flex aspect-[3/2] items-center justify-center bg-paper-2 p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={nearest.id}
              src={imageUrl(nearest.id, 480)}
              alt={nearest.record ? photoTitle(nearest.record) : nearest.id}
              className="fade-in max-h-full max-w-full object-contain"
            />
          </div>
          <div>
            <p className="font-medium">{nearest.record ? photoTitle(nearest.record) : nearest.id}</p>
            <p className="mt-0.5 font-mono text-meta text-ink-muted">
              {caption(nearest)} · {Math.round(nearest.distance_m)} m entfernt
            </p>
            {nearest.record?.license && <p className="mt-0.5 text-meta text-ink-muted">{nearest.record.license.credit}</p>}
            {nearest.id !== currentId && (
              <Link href={analyseHref(nearest.id)} className="mt-2 inline-block text-meta text-ink-muted hover:text-ink-strong">
                Dieses Foto ansehen →
              </Link>
            )}
          </div>
        </div>
      )}

      {photos.length > 1 && (
        <ol className="mt-4 flex gap-3 overflow-x-auto pb-2">
          {photos.map((p) => (
            <li key={p.id} className="shrink-0">
              <button
                type="button"
                onClick={() => onYear(p.year)}
                className={`block border p-1 ${p === nearest ? "border-accent" : "border-transparent hover:border-rule"}`}
                title={p.record ? photoTitle(p.record) : p.id}
              >
                {/* w-36 fits "1904 · SG.CIV.12.4743" in 11px mono */}
                <span className="flex h-24 w-36 items-center justify-center bg-paper-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imageUrl(p.id, 240)} alt="" loading="lazy" className="max-h-full max-w-full object-contain" />
                </span>
                <span className={`mt-1 block font-mono text-[11px] ${p === nearest ? "text-accent" : "text-ink-muted"}`}>
                  {caption(p)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
