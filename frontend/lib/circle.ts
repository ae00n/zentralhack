// Uncertainty circle (coordinates.radius_m) as GeoJSON, shared by the detail map and the desk map.
import type { Coordinates } from "./types";

const METRES_PER_DEGREE = 111_320;

/** Ring of [lon, lat] around the centre; flat-earth maths is exact enough for a few kilometres. */
export function circleRing(c: Coordinates, steps = 64): [number, number][] {
  const dLat = c.radius_m / METRES_PER_DEGREE;
  const dLon = dLat / Math.cos((c.lat * Math.PI) / 180);
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push([c.lon + dLon * Math.cos(a), c.lat + dLat * Math.sin(a)]);
  }
  return ring;
}

export function circleData(c: Coordinates): GeoJSON.Feature<GeoJSON.Polygon> {
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [circleRing(c)] } };
}

/** [[west, south], [east, north]] of the circle. */
export function circleBox(c: Coordinates): [[number, number], [number, number]] {
  const ring = circleRing(c, 16);
  const lons = ring.map((p) => p[0]);
  const lats = ring.map((p) => p[1]);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}
