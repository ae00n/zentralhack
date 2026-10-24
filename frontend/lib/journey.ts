// The places an analysis visited, read from its trace (Said, 24.10.): the desk map replays them before it
// lands on the result, like a GeoGuessr replay. Only steps with coordinates count; nearby ones merge.
import type { AnalysisResult } from "@/lib/types";

export interface Waypoint {
  lat: number;
  lon: number;
  /** Short German label for the sign on the map, e.g. "Luftbild: Spital Schwyz". */
  label: string;
}

const MERGE_M = 150;
const MAX_STOPS = 5;

function dist(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const k = Math.PI / 180;
  const x = (b.lon - a.lon) * k * Math.cos(((a.lat + b.lat) / 2) * k);
  return 6371000 * Math.hypot(x, (b.lat - a.lat) * k);
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function point(lat: unknown, lon: unknown, label: string): Waypoint | null {
  const la = num(lat);
  const lo = num(lon);
  return la === null || lo === null ? null : { lat: la, lon: lo, label };
}

export function journeyOf(result: AnalysisResult | null): Waypoint[] {
  const out: Waypoint[] = [];
  for (const t of result?.trace ?? []) {
    if (t.type !== "tool_call" || !t.input) continue;
    const i = t.input as Record<string, unknown>;
    const found: (Waypoint | null)[] = [];
    switch (t.tool) {
      case "photos_near":
        found.push(point(i.lat, i.lon, "Fotos vor Ort"));
        break;
      case "aerial_view":
        for (const c of (i.candidates as { name?: string; lat?: number; lon?: number }[] | undefined) ?? [])
          found.push(point(c.lat, c.lon, `Luftbild: ${c.name ?? "Kandidat"}`));
        break;
      case "skyline":
        found.push(point(i.lat, i.lon, "Skyline und Sonne"));
        break;
      case "terrain_check":
        found.push(point(i.from_lat, i.from_lon, "Sichtlinie"));
        break;
      case "address_lookup":
        found.push(point(i.lat, i.lon, i.auto ? "Prüfung im Adressverzeichnis" : "Adressverzeichnis"));
        break;
      case "named_buildings":
        found.push(point(i.lat, i.lon, "Gebäude in der Nähe"));
        break;
      case "viewpoint_search": {
        const n = i.near as { lat?: number; lon?: number } | null | undefined;
        if (n) found.push(point(n.lat, n.lon, "Blickpunkt aus den Bergen"));
        break;
      }
    }
    for (const w of found) {
      if (!w) continue;
      const near = out.find((o) => dist(o, w) < MERGE_M);
      if (near) continue; // the same spot again: one stop
      out.push(w);
    }
  }
  return out.slice(0, MAX_STOPS);
}
