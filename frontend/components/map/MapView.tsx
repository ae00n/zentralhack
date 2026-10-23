"use client";

// MapLibre with one swisstopo raster layer, a pin and the uncertainty circle (radius_m).
// The layer can change (Zeitreise years, step 9); raster-fade softens the switch.
// Client only (MapLibre needs window): load it with next/dynamic and ssr: false.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { Coordinates } from "@/lib/types";

export interface MapViewProps {
  center: Coordinates;
  /** Raster template from tileTemplate(). */
  tiles: string;
  /** Highest zoom the layer has real tiles for; MapLibre scales up beyond it. zeitreihen: 16. */
  tilesMaxZoom?: number;
  /** Layer name after "© swisstopo", e.g. "SWISSIMAGE". */
  layerLabel: string;
  /** Offline the tile cache only has zoom 12 to 17 around the demo areas (question 4.2). */
  offline: boolean;
}

const METRES_PER_DEGREE = 111_320;
const FIT = { padding: 48, maxZoom: 16 };

/** Ring of [lon, lat] around the centre; flat-earth maths is exact enough for a few kilometres. */
function circleRing(c: Coordinates, steps = 64): [number, number][] {
  const dLat = c.radius_m / METRES_PER_DEGREE;
  const dLon = dLat / Math.cos((c.lat * Math.PI) / 180);
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push([c.lon + dLon * Math.cos(a), c.lat + dLat * Math.sin(a)]);
  }
  return ring;
}

function circleData(c: Coordinates): GeoJSON.Feature<GeoJSON.Polygon> {
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [circleRing(c)] } };
}

function circleBounds(c: Coordinates): maplibregl.LngLatBounds {
  return circleRing(c, 16).reduce(
    (b, p) => b.extend(p),
    new maplibregl.LngLatBounds([c.lon, c.lat], [c.lon, c.lat]),
  );
}

/** A colour token as a CSS colour: globals.css holds RGB channels ("23 23 23"), MapLibre needs rgb(...). */
function token(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v ? `rgb(${v.split(/\s+/).join(", ")})` : fallback;
}

function baseSource(tiles: string, maxzoom: number): maplibregl.RasterSourceSpecification {
  return { type: "raster", tiles: [tiles], tileSize: 256, maxzoom };
}

export default function MapView({ center, tiles, tilesMaxZoom = 19, layerLabel, offline }: MapViewProps) {
  const sourceMaxZoom = Math.min(tilesMaxZoom, offline ? 17 : 19);
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  // What the map shows now, so the effects below only act on real changes (not on mount).
  const shown = useRef({ center, tiles, sourceMaxZoom });

  // Create once; the effects below follow prop changes.
  useEffect(() => {
    if (!container.current) return;
    // Ink, not brand red: red never encodes data (FRONTPAGE_PLAN 2).
    const mark = token("--ink", "#191919");
    const m = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          base: baseSource(tiles, sourceMaxZoom),
          uncertainty: { type: "geojson", data: circleData(center) },
        },
        layers: [
          { id: "base", type: "raster", source: "base", paint: { "raster-fade-duration": 300 } },
          {
            id: "uncertainty-fill",
            type: "fill",
            source: "uncertainty",
            paint: { "fill-color": mark, "fill-opacity": 0.12 },
          },
          {
            id: "uncertainty-line",
            type: "line",
            source: "uncertainty",
            paint: { "line-color": mark, "line-width": 1.5 },
          },
        ],
      },
      bounds: circleBounds(center),
      fitBoundsOptions: FIT,
      minZoom: offline ? 12 : 7,
      maxZoom: offline ? 17 : 19,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const pin = document.createElement("div");
    pin.className = "map-pin";
    marker.current = new maplibregl.Marker({ element: pin }).setLngLat([center.lon, center.lat]).addTo(m);
    map.current = m;
    shown.current = { center, tiles, sourceMaxZoom };
    // The container can still change size while the page lays out; fit once more when the map is ready.
    m.once("load", () => {
      m.resize();
      m.fitBounds(circleBounds(center), { ...FIT, duration: 0 });
    });

    return () => {
      marker.current = null;
      map.current = null;
      m.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- later changes are applied below
  }, []);

  useEffect(() => {
    const m = map.current;
    const prev = shown.current.center;
    if (!m || (prev.lat === center.lat && prev.lon === center.lon && prev.radius_m === center.radius_m)) return;
    shown.current.center = center;
    marker.current?.setLngLat([center.lon, center.lat]);
    const apply = () => {
      (m.getSource("uncertainty") as maplibregl.GeoJSONSource | undefined)?.setData(circleData(center));
      m.fitBounds(circleBounds(center), { ...FIT, duration: 400 });
    };
    if (m.isStyleLoaded()) apply();
    else m.once("load", apply);
  }, [center.lat, center.lon, center.radius_m]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const m = map.current;
    if (!m || (shown.current.tiles === tiles && shown.current.sourceMaxZoom === sourceMaxZoom)) return;
    const sameZoom = shown.current.sourceMaxZoom === sourceMaxZoom;
    shown.current.tiles = tiles;
    shown.current.sourceMaxZoom = sourceMaxZoom;
    const apply = () => {
      if (sameZoom) {
        (m.getSource("base") as maplibregl.RasterTileSource | undefined)?.setTiles([tiles]);
        return;
      }
      // A source's maxzoom is fixed, so swapping SWISSIMAGE (19) and zeitreihen (16) rebuilds it.
      m.removeLayer("base");
      m.removeSource("base");
      m.addSource("base", baseSource(tiles, sourceMaxZoom));
      m.addLayer({ id: "base", type: "raster", source: "base", paint: { "raster-fade-duration": 300 } }, "uncertainty-fill");
    };
    if (m.isStyleLoaded()) apply();
    else m.once("load", apply);
  }, [tiles, sourceMaxZoom]);

  return (
    <div className="relative h-full w-full">
      {/* Sized by h-full, not absolute inset-0: maplibre-gl.css sets .maplibregl-map to position: relative. */}
      <div ref={container} className="h-full w-full" />
      <p className="pointer-events-none absolute bottom-0 right-0 bg-paper px-1.5 py-0.5 text-meta text-ink-muted">
        © swisstopo · {layerLabel}
      </p>
    </div>
  );
}
