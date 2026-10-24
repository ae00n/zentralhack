// Is there Google Street View near a spot (Said, 24.10.)? Reads Google's coverage layer (the blue lines,
// keyless PNG tiles with open CORS) around the spot and returns the nearest covered point within 80 m, or
// null. The desk opens its street view pane only on a hit, so a mountain or a field shows no empty pane.
// Checked on 16 real results: 9 hits (7 to 47 m away), 7 without coverage.

const Z = 17; // about 0.8 m per pixel in Schwyz
const RADIUS_M = 80;
const TIMEOUT_MS = 2500;
const TILE = 256;

export interface StreetSpot {
  lat: number;
  lon: number;
  /** Distance from the asked spot to the covered point, in metres. */
  metres: number;
}

const cache = new Map<string, Promise<StreetSpot | null>>();

function world(lat: number, lon: number): [number, number] {
  const n = 2 ** Z * TILE;
  const s = Math.sin((lat * Math.PI) / 180);
  return [((lon + 180) / 360) * n, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n];
}

function unworld(px: number, py: number): { lat: number; lon: number } {
  const n = 2 ** Z * TILE;
  return { lat: (Math.atan(Math.sinh(Math.PI * (1 - (2 * py) / n))) * 180) / Math.PI, lon: (px / n) * 360 - 180 };
}

/** The alpha channel of one coverage tile (empty tiles come back tiny and are scaled up, still empty). */
function alpha(x: number, y: number): Promise<Uint8ClampedArray> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = c.height = TILE;
      const g = c.getContext("2d", { willReadFrequently: true });
      if (!g) return reject(new Error("no canvas"));
      g.drawImage(img, 0, 0, TILE, TILE);
      resolve(g.getImageData(0, 0, TILE, TILE).data);
    };
    img.onerror = () => reject(new Error("tile"));
    img.src = `https://mts1.googleapis.com/vt?hl=de&lyrs=svv|cb_client:apiv3&style=40,18&x=${x}&y=${y}&z=${Z}`;
  });
}

async function search(lat: number, lon: number): Promise<StreetSpot | null> {
  const mpp = (156543.03 * Math.cos((lat * Math.PI) / 180)) / 2 ** Z;
  const r = RADIUS_M / mpp;
  const [px, py] = world(lat, lon);
  const jobs: Promise<{ x: number; y: number; a: Uint8ClampedArray }>[] = [];
  for (let x = Math.floor((px - r) / TILE); x <= Math.floor((px + r) / TILE); x++)
    for (let y = Math.floor((py - r) / TILE); y <= Math.floor((py + r) / TILE); y++)
      jobs.push(alpha(x, y).then((a) => ({ x, y, a })));
  let best: { d: number; px: number; py: number } | null = null;
  for (const { x, y, a } of await Promise.all(jobs)) {
    for (let j = 0; j < TILE; j++)
      for (let i = 0; i < TILE; i++) {
        if (a[(j * TILE + i) * 4 + 3] < 128) continue;
        const qx = x * TILE + i + 0.5;
        const qy = y * TILE + j + 0.5;
        const d = Math.hypot(qx - px, qy - py);
        if (d <= r && (!best || d < best.d)) best = { d, px: qx, py: qy };
      }
  }
  return best ? { ...unworld(best.px, best.py), metres: Math.round(best.d * mpp) } : null;
}

/** The nearest point with Street View within 80 m of the spot; null when none, offline or slow. */
export function nearestStreetView(lat: number, lon: number): Promise<StreetSpot | null> {
  const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const p = Promise.race([
    search(lat, lon),
    new Promise<null>((resolve) => setTimeout(() => resolve(null), TIMEOUT_MS)),
  ])
    .catch(() => null)
    .then((v) => {
      if (!v) cache.delete(key); // no coverage, offline or slow: ask again next time (tiles are browser cached)
      return v;
    });
  cache.set(key, p);
  return p;
}
