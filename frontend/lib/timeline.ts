// Zeitreise logic (build step 9): slider years, snapping to valid zeitreihen TIME values, photo years.
import type { AnalysisResult, TimelinePhoto } from "./types";

/** Slider range: the first zeitreihen sheet the spec promises, up to today. */
export const FIRST_YEAR = 1864;
export const THIS_YEAR = new Date().getFullYear();

/** What the map shows for a slider year: a zeitreihen TIME, or today's SWISSIMAGE. */
export type MapTime = { kind: "zeitreihen"; time: number; year: number } | { kind: "heute" };

/**
 * Nearest valid TIME for a year (map_years like 18641231, from /timeline). Years after the last
 * sheet show SWISSIMAGE. Only values from map_years are ever returned, so no tile request gets
 * an invalid TIME (swisstopo answers those with HTTP 400).
 */
export function snapToMap(year: number, mapYears: number[]): MapTime {
  if (mapYears.length === 0) return { kind: "heute" };
  const sorted = [...mapYears].sort((a, b) => a - b);
  const last = sorted[sorted.length - 1];
  if (year > Math.floor(last / 10000)) return { kind: "heute" };
  let best = sorted[0];
  for (const t of sorted) {
    if (Math.abs(Math.floor(t / 10000) - year) < Math.abs(Math.floor(best / 10000) - year)) best = t;
  }
  return { kind: "zeitreihen", time: best, year: Math.floor(best / 10000) };
}

/** One year for a dated photo: exact year, or the middle of its range. null when undated. */
export function photoYear(p: Pick<TimelinePhoto, "year_from" | "year_to">): number | null {
  const { year_from: a, year_to: b } = p;
  if (a === null && b === null) return null;
  if (a === null || b === null) return (a ?? b) as number;
  return Math.round((a + b) / 2);
}

/** Dated photos sorted by year; undated ones cannot sit on the axis. */
export function datedPhotos(photos: TimelinePhoto[]): (TimelinePhoto & { year: number })[] {
  return photos
    .flatMap((p) => {
      const year = photoYear(p);
      return year === null ? [] : [{ ...p, year }];
    })
    .sort((a, b) => a.year - b.year || a.distance_m - b.distance_m);
}

/** The photo nearest to a year (closer place wins a tie). */
export function nearestPhoto<T extends { year: number; distance_m: number }>(photos: T[], year: number): T | null {
  let best: T | null = null;
  for (const p of photos) {
    if (
      !best ||
      Math.abs(p.year - year) < Math.abs(best.year - year) ||
      (Math.abs(p.year - year) === Math.abs(best.year - year) && p.distance_m < best.distance_m)
    )
      best = p;
  }
  return best;
}

/** Where the slider starts: the analysis' own year estimate, so the map first shows the photo's time. */
export function estimatedYear(result: AnalysisResult): number | null {
  const range = result.fields.year_range?.value;
  if (range && (range.from !== null || range.to !== null)) return photoYear({ year_from: range.from, year_to: range.to });
  const decade = result.fields.decade?.value;
  return typeof decade === "number" ? decade + 5 : null;
}

export function clampYear(year: number): number {
  return Math.min(THIS_YEAR, Math.max(FIRST_YEAR, year));
}
