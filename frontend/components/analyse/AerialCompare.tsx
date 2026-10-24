"use client";

// What the agent looked at in an "aerial_view" step (Said, 24.10.): the swisstopo aerial photo of each
// candidate, as of the photo's capture year, side by side with a red cross on the candidate. Drawn from the
// step's input (candidate coordinates), so the backend need not keep the pictures. swisstopo open data.
import { useState } from "react";
import { tileTemplate } from "@/lib/api";

export interface AerialCandidate {
  name: string;
  lat: number;
  lon: number;
}

interface Props {
  candidates: AerialCandidate[];
  radiusM: number;
  tilesUrl: string;
  /** Capture year: the time series layer gives the latest flight up to it. */
  year?: number;
}

const W = 168;
const H = 126;
const TILE = 256;

function zoomFor(lat: number, radiusM: number): number {
  const metresPerPx = (2 * radiusM) / W;
  const z = Math.log2((156543.03 * Math.cos((lat * Math.PI) / 180)) / metresPerPx);
  return Math.max(15, Math.min(19, Math.round(z)));
}

function worldPx(lat: number, lon: number, z: number): [number, number] {
  const n = 2 ** z * TILE;
  const s = Math.sin((lat * Math.PI) / 180);
  return [((lon + 180) / 360) * n, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n];
}

function Tiles({ c, radiusM, template, fallback }: { c: AerialCandidate; radiusM: number; template: string; fallback: string }) {
  const z = zoomFor(c.lat, radiusM);
  const [px, py] = worldPx(c.lat, c.lon, z);
  const left = px - W / 2;
  const top = py - H / 2;
  const tiles: { x: number; y: number }[] = [];
  for (let x = Math.floor(left / TILE); x <= Math.floor((left + W) / TILE); x++)
    for (let y = Math.floor(top / TILE); y <= Math.floor((top + H) / TILE); y++) tiles.push({ x, y });
  const url = (t: string, x: number, y: number) => t.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  return (
    <>
      {tiles.map(({ x, y }) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={`${x}-${y}`}
          src={url(template, x, y)}
          alt=""
          draggable={false}
          onError={(e) => {
            const img = e.currentTarget;
            const current = url(fallback, x, y);
            if (img.src !== current) img.src = current; // no flight that year: the current photo
          }}
          className="absolute max-w-none"
          style={{ left: x * TILE - left, top: y * TILE - top, width: TILE, height: TILE }}
        />
      ))}
    </>
  );
}

export default function AerialCompare({ candidates, radiusM, tilesUrl, year }: Props) {
  const [open, setOpen] = useState<number | null>(null);
  const series = tileTemplate(tilesUrl, "ch.swisstopo.swissimage-product", year ?? "current");
  const current = tileTemplate(tilesUrl, "ch.swisstopo.swissimage", "current");
  const shown = candidates.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon)).slice(0, 4);
  if (shown.length === 0) return null;
  return (
    <div className="mt-1.5">
      <div className="flex flex-wrap gap-2">
        {shown.map((c, i) => (
          <button
            key={`${c.name}-${i}`}
            type="button"
            onClick={() => setOpen(open === i ? null : i)}
            className="group text-left"
            aria-label={`Luftbild ${c.name}`}
          >
            <span
              className="aerial-tile relative block overflow-hidden rounded-sm border border-rule/[0.12] bg-paper-2"
              style={{ width: W, height: H, animationDelay: `${i * 140}ms` }}
            >
              <Tiles c={c} radiusM={radiusM} template={series} fallback={current} />
              <span aria-hidden className="absolute left-1/2 top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2">
                <span className="absolute left-1/2 top-0 h-full w-[2px] -translate-x-1/2 bg-accent shadow-[0_0_0_1px_#fff]" />
                <span className="absolute left-0 top-1/2 h-[2px] w-full -translate-y-1/2 bg-accent shadow-[0_0_0_1px_#fff]" />
              </span>
            </span>
            <span className="mt-0.5 block max-w-[168px] truncate text-micro text-ink-muted group-hover:text-ink">{c.name}</span>
          </button>
        ))}
      </div>
      <p className="mt-0.5 text-micro text-ink-muted">
        Luftbild swisstopo{year ? `, Stand ${year}` : ""}, {Math.round(2 * radiusM)} m breit, Norden oben
      </p>
    </div>
  );
}
