"use client";

// Desk map (FRONTPAGE_PLAN 4, "Map spec"): swisstopo grey map, canton outline with the outside veiled
// white, one circle per place coloured by certainty, hover and selection via feature-state.
// Client only (MapLibre needs window): load with next/dynamic and ssr: false.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { CertClass, Place } from "@/lib/desk";

export interface DeskMapProps {
  places: Place[];
  /** Raster template for ch.swisstopo.pixelkarte-grau (online WMTS or the offline /tiles route). */
  tiles: string;
  offline: boolean;
  hoveredPlace: number | null;
  selectedPlace: number | null;
  onHover: (placeId: number | null) => void;
  /** A pin with one photo. */
  onPickPhoto: (photoId: string) => void;
  /** Signature shown in the popup of a place with several photos. */
  labelOf: (photoId: string) => string;
}

const BOUNDS: [[number, number], [number, number]] = [
  [8.3856, 46.8901],
  [9.0061, 47.2199],
];
const MAX_BOUNDS: [[number, number], [number, number]] = [
  [8.1, 46.75],
  [9.3, 47.36],
];
const WORLD: [number, number][] = [
  [-180, -85],
  [180, -85],
  [180, 85],
  [-180, 85],
  [-180, -85],
];

/** A colour token as a CSS colour: globals.css holds RGB channels ("23 23 23"), MapLibre needs rgb(...). */
function token(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v ? `rgb(${v.split(/\s+/).join(", ")})` : fallback;
}

function placesData(places: Place[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: places.map((p) => ({
      type: "Feature",
      id: p.id,
      properties: { count: p.count, worst: p.worst },
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    })),
  };
}

/** World minus canton: the mask that veils everything outside Schwyz. */
function maskOf(canton: GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>): GeoJSON.Feature<GeoJSON.Polygon> {
  const g = canton.geometry;
  const outers = g.type === "Polygon" ? [g.coordinates[0]] : g.coordinates.map((poly) => poly[0]);
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [WORLD, ...outers] } };
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Room for the floating list panel (400 px + 12 px inset) on wide screens; plain padding on the phone. */
function framePadding(): maplibregl.PaddingOptions {
  return window.matchMedia("(min-width: 1024px)").matches
    ? { left: 424, top: 24, right: 24, bottom: 24 }
    : { left: 24, top: 24, right: 24, bottom: 24 };
}

export default function DeskMap({
  places,
  tiles,
  offline,
  hoveredPlace,
  selectedPlace,
  onHover,
  onPickPhoto,
  labelOf,
}: DeskMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const counts = useRef<maplibregl.Marker[]>([]);
  const popup = useRef<maplibregl.Popup | null>(null);
  // Latest props for the map event handlers, which are bound once.
  const latest = useRef({ places, onHover, onPickPhoto, labelOf });
  latest.current = { places, onHover, onPickPhoto, labelOf };
  const state = useRef<{ hovered: number | null; selected: number | null }>({ hovered: null, selected: null });

  // Create once.
  useEffect(() => {
    if (!container.current) return;
    const color: Record<CertClass, string> = {
      confirmed: token("--cert-confirmed", "#0b3c5d"),
      sure: token("--cert-sure", "#1d4e89"),
      check: token("--cert-check", "#b35806"),
      open: token("--cert-open", "#595959"),
    };
    const accent = token("--accent", "#e2001a");
    const byClass = (cls: CertClass) => ["==", ["get", "worst"], cls];
    const fillByClass: maplibregl.ExpressionSpecification = [
      "case",
      byClass("confirmed"),
      color.confirmed,
      byClass("sure"),
      color.sure,
      byClass("check"),
      color.check,
      "rgba(255,255,255,0.9)",
    ] as unknown as maplibregl.ExpressionSpecification;
    // Polish 5: radius by zoom (z8 4 px, z14 7 px), a place with several photos 1.5 px larger, hover +2.
    // Zoom must be the input of the top-level interpolate, so the bonus sits in each stop.
    const bonus = (base: number) =>
      [
        "+",
        base,
        ["case", [">", ["get", "count"], 1], 1.5, 0],
        ["case", ["boolean", ["feature-state", "hover"], false], 2, 0],
      ] as unknown as number;
    const radius = ["interpolate", ["linear"], ["zoom"], 8, bonus(4), 14, bonus(7)] as unknown as maplibregl.ExpressionSpecification;
    const ringRadius = (extra: number) =>
      ["interpolate", ["linear"], ["zoom"], 8, ["+", bonus(4), extra], 14, ["+", bonus(7), extra]] as unknown as maplibregl.ExpressionSpecification;
    // Sure and reviewed places draw on top of the uncertain ones.
    const sortKey = ["match", ["get", "worst"], "open", 0, "check", 1, "sure", 2, 3] as unknown as maplibregl.ExpressionSpecification;

    const m = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          base: { type: "raster", tiles: [tiles], tileSize: 256, maxzoom: offline ? 16 : 18 },
          places: { type: "geojson", data: placesData(places) },
        },
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#fafafa" } },
          {
            id: "base",
            type: "raster",
            source: "base",
            // Softened raster (polish 5): grey, less contrast, a bit lighter, so the dots carry the colour.
            paint: {
              "raster-saturation": -1,
              "raster-contrast": -0.15,
              "raster-brightness-min": 0.12,
              "raster-brightness-max": 0.98,
              "raster-opacity": 0.85,
              "raster-fade-duration": 300,
            },
          },
        ],
      },
      bounds: BOUNDS,
      fitBoundsOptions: { padding: framePadding() },
      maxBounds: MAX_BOUNDS,
      minZoom: 8,
      maxZoom: offline ? 16 : 18,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    // An integer zoom keeps the raster labels crisp instead of scaled.
    m.once("load", () => m.setZoom(Math.round(m.getZoom())));

    m.on("load", async () => {
      try {
        const canton = (await (await fetch("/geo/kanton-schwyz.json")).json()) as GeoJSON.Feature<
          GeoJSON.Polygon | GeoJSON.MultiPolygon
        >;
        m.addSource("mask", { type: "geojson", data: maskOf(canton) });
        m.addSource("canton", { type: "geojson", data: canton });
        m.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#ffffff", "fill-opacity": 0.75 } });
        m.addLayer({
          id: "canton-line",
          type: "line",
          source: "canton",
          paint: { "line-color": "#1a1a1a", "line-width": 1.25, "line-opacity": 0.6 },
        });
      } catch {
        // Without the outline the map still works.
      }
      // Dots in layers (polish 5): soft shadow, reviewed outer ring, the dot, and the selection ring on top.
      m.addLayer({
        id: "places-shadow",
        type: "circle",
        source: "places",
        layout: { "circle-sort-key": sortKey },
        paint: {
          "circle-radius": ringRadius(1),
          "circle-color": "#000000",
          "circle-opacity": 0.18,
          "circle-blur": 1,
          "circle-translate": [0, 1],
        },
      });
      m.addLayer({
        id: "places-ring",
        type: "circle",
        source: "places",
        filter: byClass("confirmed") as maplibregl.FilterSpecification,
        paint: {
          "circle-radius": ringRadius(2.5),
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": color.confirmed,
          "circle-stroke-width": 2,
        },
      });
      m.addLayer({
        id: "places",
        type: "circle",
        source: "places",
        layout: { "circle-sort-key": sortKey },
        paint: {
          "circle-radius": radius,
          "circle-color": fillByClass,
          // White 1.5 px stroke; "nicht bestimmbar" is hollow with a grey stroke.
          "circle-stroke-color": ["case", byClass("open"), color.open, "#ffffff"] as unknown as maplibregl.ExpressionSpecification,
          "circle-stroke-width": 1.5,
        },
      });
      // Selection: a separate red ring, radius +4, no fill; only the selected place shows it.
      m.addLayer({
        id: "places-selected",
        type: "circle",
        source: "places",
        paint: {
          "circle-radius": ringRadius(4),
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": accent,
          "circle-stroke-width": 3,
          "circle-stroke-opacity": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            1,
            0,
          ] as unknown as maplibregl.ExpressionSpecification,
        },
      });
      ready.current = true;
      applyState(m);
      drawCounts(m);
    });

    m.on("mousemove", "places", (e) => {
      m.getCanvas().style.cursor = "pointer";
      const id = e.features?.[0]?.id;
      if (typeof id === "number" && id !== state.current.hovered) latest.current.onHover(id);
    });
    m.on("mouseleave", "places", () => {
      m.getCanvas().style.cursor = "";
      latest.current.onHover(null);
    });
    m.on("click", "places", (e) => {
      const id = e.features?.[0]?.id;
      const place = latest.current.places.find((p) => p.id === id);
      if (!place) return;
      if (place.count === 1) {
        latest.current.onPickPhoto(place.ids[0]);
        return;
      }
      // Several photos at one spot (often a Fotoserie): a small list to pick from.
      const box = document.createElement("div");
      box.className = "desk-popup";
      const head = document.createElement("p");
      head.textContent = `${place.count} Fotos an diesem Ort`;
      box.appendChild(head);
      for (const photoId of place.ids) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = latest.current.labelOf(photoId);
        b.onclick = () => {
          popup.current?.remove();
          latest.current.onPickPhoto(photoId);
        };
        box.appendChild(b);
      }
      popup.current?.remove();
      popup.current = new maplibregl.Popup({ closeButton: true, offset: 14, maxWidth: "240px" })
        .setLngLat([place.lon, place.lat])
        .setDOMContent(box)
        .addTo(m);
    });

    // The phone tabs hide the map (display: none); resize when it shows again.
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(container.current);

    map.current = m;
    // Test hook for the headless checks (dev only): read feature-state and project pins to pixels.
    if (process.env.NODE_ENV !== "production") (window as unknown as { __deskMap?: maplibregl.Map }).__deskMap = m;
    return () => {
      ro.disconnect();
      ready.current = false;
      counts.current.forEach((c) => c.remove());
      counts.current = [];
      map.current = null;
      m.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- later changes are applied below
  }, []);

  /** Feature-state for hover and selection; setData resets it, so this runs after every data change. */
  function applyState(m: maplibregl.Map) {
    if (!ready.current) return;
    m.removeFeatureState({ source: "places" });
    const { hovered, selected } = state.current;
    if (hovered !== null) m.setFeatureState({ source: "places", id: hovered }, { hover: true });
    if (selected !== null) m.setFeatureState({ source: "places", id: selected }, { selected: true });
  }

  /** Count labels as HTML markers (a raster-only style has no glyphs for a symbol layer, and offline none). */
  function drawCounts(m: maplibregl.Map) {
    counts.current.forEach((c) => c.remove());
    counts.current = latest.current.places
      .filter((p) => p.count > 1)
      .map((p) => {
        const el = document.createElement("div");
        el.className = "desk-count";
        el.textContent = String(p.count);
        return new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(m);
      });
  }

  // Data changes (results arrive, reviews change the classes).
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    (m.getSource("places") as maplibregl.GeoJSONSource | undefined)?.setData(placesData(places));
    applyState(m);
    drawCounts(m);
  }, [places]);

  useEffect(() => {
    const m = map.current;
    const prevSelected = state.current.selected;
    state.current = { hovered: hoveredPlace, selected: selectedPlace };
    if (!m) return;
    applyState(m);
    // Fly to a newly selected place (jumpTo under reduced motion).
    if (selectedPlace !== null && selectedPlace !== prevSelected) {
      const p = latest.current.places.find((x) => x.id === selectedPlace);
      if (p) {
        const target = { center: [p.lon, p.lat] as [number, number], zoom: Math.max(m.getZoom(), 13), padding: framePadding() };
        if (reducedMotion()) m.jumpTo(target);
        else m.easeTo({ ...target, duration: 450 });
      }
    }
  }, [hoveredPlace, selectedPlace]);

  return (
    <div role="region" aria-label="Karte der Fotostandorte" className="relative h-full w-full">
      <div ref={container} className="h-full w-full" />
      <p className="pointer-events-none absolute bottom-0 right-0 bg-paper px-1.5 py-0.5 text-meta text-ink-muted">© swisstopo</p>
    </div>
  );
}
