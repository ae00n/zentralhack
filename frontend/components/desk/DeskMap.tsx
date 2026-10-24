"use client";

// Desk map (FRONTPAGE_PLAN 4, "Map spec"): swisstopo aerial photo or colour map (grey offline), canton outline,
// one circle per place coloured by certainty, hover and selection via feature-state. A newly picked place is
// reached with a flight that zooms out to the canton and back in.
// Client only (MapLibre needs window): load with next/dynamic and ssr: false.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import { circleBox, circleData } from "@/lib/circle";
import type { CertClass, Place } from "@/lib/desk";

export interface DeskMapProps {
  places: Place[];
  /** Raster template for ch.swisstopo.pixelkarte-farbe online, pixelkarte-grau on the offline /tiles route. */
  tiles: string;
  /** The tiles are pixelkarte-grau: soften them to grey instead of keeping colour. */
  grey: boolean;
  /** Raster template for ch.swisstopo.swissimage (the "Luftbild" background). */
  aerialTiles: string;
  basemap: "karte" | "luftbild";
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
const CANTON_CENTRE: [number, number] = [8.696, 47.055];
const FIRST_ZOOM = 11.6;
// Close-up on a picked place; a fractional zoom for the same reason as FIRST_ZOOM (detailed tiles, small labels).
const PICK_ZOOM = 14.6; // closer on a picked photo (Said, 24.10.)
const PICK_FLOOR = 13;
// The flight to a newly picked photo (Said, 24.10.): rise to all of Switzerland, mark the target with a
// beacon, dive in with a slight drone tilt, settle flat. Offline only the canton is cached, so it rises to
// the canton instead.
const SWISS_BOUNDS: [[number, number], [number, number]] = [
  [5.956, 45.818],
  [10.492, 47.808],
];
const RISE_MS = 850;
const HOLD_MS = 180;
const DIVE_MS = 1450;
const SETTLE_MS = 420;
// Every flight takes its own route (Said, 24.10.): the camera rises off to a new side of the target (never
// the side of the last flight) and dives back in with a tilt and turn that vary.
const RISE_OFFSET_DEG = 1.1; // how far the high point lies from the target, in degrees of latitude
const DIVE_PITCH: [number, number] = [38, 52];
const DIVE_BEARING: [number, number] = [8, 20];
const between = ([a, b]: [number, number]) => a + Math.random() * (b - a);
const MIN_ZOOM = 8;
// Europe underneath for the high part of the flight: swisstopo tiles are white outside Switzerland, so they
// fade in only from FADE_FROM to FADE_TO. Sentinel-2 cloudless 2020 by EOX (CC BY-NC-SA 4.0), online only.
const WORLD_TILES = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg";
const FADE_FROM = 7.5;
// The swisstopo WMTS extent (WGS84 west, south, east, north) and the lowest zoom we load from it.
const SWISS_EXTENT: [number, number, number, number] = [5.14, 45.39, 11.48, 48.23];
const SWISS_MINZOOM = 7;
const FADE_TO = 9;
const fadeIn = (opacity: number) =>
  ["interpolate", ["linear"], ["zoom"], FADE_FROM, 0, FADE_TO, opacity] as unknown as maplibregl.ExpressionSpecification;
const easeOut = (t: number) => 1 - (1 - t) ** 3;
const easeInOut = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const NO_CIRCLE: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const MAX_BOUNDS: [[number, number], [number, number]] = [
  [8.1, 46.75],
  [9.3, 47.36],
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

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Room for the floating list panel (400 px + 12 px inset) on wide screens; plain padding on the phone. */
function framePadding(): Required<maplibregl.PaddingOptions> {
  return window.matchMedia("(min-width: 1024px)").matches
    ? { left: 424, top: 24, right: 24, bottom: 24 }
    : { left: 24, top: 24, right: 24, bottom: 24 };
}

export default function DeskMap({
  places,
  tiles,
  grey,
  aerialTiles,
  basemap,
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
  const pin = useRef<maplibregl.Marker | null>(null);
  const beacon = useRef<maplibregl.Marker | null>(null);
  // Flight number: a newer pick or a hand on the map ends the running flight.
  const flight = useRef(0);
  // Compass direction of the last flight's high point, so the next one comes from another side.
  const lastSide = useRef<number | null>(null);
  // Latest props for the map event handlers, which are bound once.
  const latest = useRef({ places, basemap, onHover, onPickPhoto, labelOf });
  latest.current = { places, basemap, onHover, onPickPhoto, labelOf };
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
    const ink = token("--ink", "#191919");
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
          // swisstopo answers 400 outside its extent: bounds and minzoom keep MapLibre from asking (the
          // Europe layer covers those zooms), so the flight causes no failed tile requests.
          base: { type: "raster", tiles: [tiles], tileSize: 256, minzoom: SWISS_MINZOOM, maxzoom: offline ? 16 : 18, bounds: SWISS_EXTENT },
          world: { type: "raster", tiles: [WORLD_TILES], tileSize: 256, maxzoom: 12 },
          aerial: { type: "raster", tiles: [aerialTiles], tileSize: 256, minzoom: SWISS_MINZOOM, maxzoom: offline ? 17 : 19, bounds: SWISS_EXTENT },
          places: { type: "geojson", data: placesData(places) },
        },
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#fafafa" } },
          // Europe from space, under both backgrounds; only seen while the camera is high (the flight).
          ...(offline ? [] : [{ id: "world", type: "raster" as const, source: "world", paint: { "raster-fade-duration": 200 } }]),
          {
            id: "base",
            type: "raster",
            source: "base",
            layout: { visibility: basemap === "karte" ? "visible" : "none" },
            // Softened raster (polish 5): less contrast and a bit lighter, so the dots stay readable.
            // The grey offline map loses all colour; the colour map keeps most of it.
            paint: grey
              ? {
                  "raster-saturation": -1,
                  "raster-contrast": -0.15,
                  "raster-brightness-min": 0.12,
                  "raster-brightness-max": 0.98,
                  "raster-opacity": offline ? 0.85 : fadeIn(0.85),
                  "raster-fade-duration": 300,
                }
              : {
                  "raster-saturation": -0.15,
                  "raster-contrast": -0.1,
                  "raster-brightness-min": 0.05,
                  "raster-opacity": offline ? 0.9 : fadeIn(0.9),
                  "raster-fade-duration": 300,
                },
          },
          // Aerial photo as is; only one of the two backgrounds is visible, so only its tiles load.
          {
            id: "aerial",
            type: "raster",
            source: "aerial",
            layout: { visibility: basemap === "luftbild" ? "visible" : "none" },
            paint: { "raster-fade-duration": 300, "raster-opacity": offline ? 1 : fadeIn(1) },
          },
        ],
      },
      bounds: BOUNDS,
      fitBoundsOptions: { padding: framePadding() },
      maxBounds: MAX_BOUNDS,
      minZoom: MIN_ZOOM,
      maxZoom: offline ? 16 : 18,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    // First view closer than the whole canton, so the map reads as detailed (Timo, 24.10.), still centred
    // in the free area. swisstopo's coarse zooms are upscaled small-scale maps with huge labels; at
    // FIRST_ZOOM MapLibre picks the detailed tiles and draws them a bit smaller. Capped on narrow screens.
    m.once("load", () =>
      m.jumpTo({ center: CANTON_CENTRE, zoom: Math.min(FIRST_ZOOM, m.getZoom() + 2), padding: framePadding() }),
    );

    m.on("load", async () => {
      try {
        const canton = (await (await fetch("/geo/kanton-schwyz.json")).json()) as GeoJSON.Feature<
          GeoJSON.Polygon | GeoJSON.MultiPolygon
        >;
        void addBorder(m); // in the background: it must not hold up the dots
        // No veil outside the canton (Said, 24.10.): MAX_BOUNDS keeps the view on the canton, so the offline
        // tile cache never shows blank tiles. A white casing keeps the outline readable on the aerial photo.
        m.addSource("canton", { type: "geojson", data: canton });
        m.addLayer({
          id: "canton-casing",
          type: "line",
          source: "canton",
          paint: { "line-color": "#ffffff", "line-width": 3, "line-opacity": 0.55 },
        });
        m.addLayer({
          id: "canton-line",
          type: "line",
          source: "canton",
          paint: { "line-color": "#1a1a1a", "line-width": 1.25, "line-opacity": 0.7 },
        });
      } catch {
        // Without the outline the map still works.
      }
      // Uncertainty circle (radius_m) of the selected place, under the dots; ink like the detail map,
      // with a white casing so it also reads on the aerial photo.
      m.addSource("uncertainty", { type: "geojson", data: NO_CIRCLE });
      m.addLayer({ id: "uncertainty-fill", type: "fill", source: "uncertainty", paint: { "fill-color": ink, "fill-opacity": 0.12 } });
      m.addLayer({
        id: "uncertainty-casing",
        type: "line",
        source: "uncertainty",
        paint: { "line-color": "#ffffff", "line-width": 3.5, "line-opacity": 0.7 },
      });
      m.addLayer({ id: "uncertainty-line", type: "line", source: "uncertainty", paint: { "line-color": ink, "line-width": 1.5 } });
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
      // Places that arrived while the style was loading were skipped by the data effect: draw the latest now.
      (m.getSource("places") as maplibregl.GeoJSONSource | undefined)?.setData(placesData(latest.current.places));
      applyBasemap(m);
      applyState(m);
      drawCounts(m);
      drawCircle(m);
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

    // A hand on the map ends a running flight where it is (and restores the canton limits).
    const takeOver = (e: { originalEvent?: unknown }) => {
      if (!e.originalEvent || !beacon.current) return;
      flight.current++;
      endFlight(m);
      placePin(m, state.current.selected, true);
      // Hand rotation is off on the desk, so level the drone tilt once the hand lets go.
      m.once("moveend", () => m.easeTo({ pitch: 0, bearing: 0, duration: 300 }));
    };
    m.on("dragstart", takeOver);
    m.on("wheel", takeOver);
    m.on("touchstart", takeOver);

    map.current = m;
    // Test hook for the headless checks (dev only): read feature-state and project pins to pixels.
    if (process.env.NODE_ENV !== "production") (window as unknown as { __deskMap?: maplibregl.Map }).__deskMap = m;
    return () => {
      ro.disconnect();
      ready.current = false;
      counts.current.forEach((c) => c.remove());
      counts.current = [];
      pin.current = null;
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

  /**
   * The Swiss border as a strong white line with a soft glow (Said, 24.10.), seen best during the flight.
   * swisstopo swissBOUNDARIES3D, simplified to about 70 m (public/geo/schweiz.json). Loaded after the rest
   * of the style, so it goes in under the canton outline and the dots.
   */
  async function addBorder(m: maplibregl.Map) {
    try {
      const ch = await (await fetch("/geo/schweiz.json")).json();
      if (map.current !== m) return;
      const below = ["canton-casing", "uncertainty-fill", "places-shadow"].find((id) => m.getLayer(id));
      m.addSource("switzerland", { type: "geojson", data: ch });
      m.addLayer(
        {
          id: "switzerland-glow",
          type: "line",
          source: "switzerland",
          paint: {
            "line-color": "#ffffff",
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 7, 9, 10, 13, 8],
            "line-blur": 6,
            "line-opacity": 0.45,
          },
        },
        below,
      );
      m.addLayer(
        {
          id: "switzerland-line",
          type: "line",
          source: "switzerland",
          layout: { "line-join": "round" },
          paint: {
            "line-color": "#ffffff",
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2.2, 9, 3, 13, 2.5],
            "line-opacity": 0.95,
          },
        },
        below,
      );
    } catch {
      // Without the national border the map still works.
    }
  }

  /** One leg of the flight; resolves when it ends, false when a newer flight or the user took over. */
  function leg(m: maplibregl.Map, id: number, run: () => void): Promise<boolean> {
    return new Promise((resolve) => {
      m.once("moveend", () => resolve(flight.current === id));
      run();
    });
  }

  function endFlight(m: maplibregl.Map) {
    beacon.current?.remove();
    beacon.current = null;
    m.setMinZoom(MIN_ZOOM);
    m.setMaxBounds(MAX_BOUNDS);
  }

  /** Pulsing rings on the target while the camera is up high, so the eye knows where it will land. */
  function showBeacon(m: maplibregl.Map, p: Place) {
    beacon.current?.remove();
    const el = document.createElement("div");
    el.className = "desk-beacon";
    el.innerHTML = "<span></span><span></span><span></span><i></i>";
    beacon.current = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat([p.lon, p.lat]).addTo(m);
  }

  /** Rise to Switzerland, beacon, dive with a drone tilt, settle flat, drop the pin. */
  async function fly(m: maplibregl.Map, p: Place, target: { center: [number, number]; zoom: number; padding: maplibregl.PaddingOptions }) {
    const id = ++flight.current;
    m.stop();
    m.setMaxBounds(null);
    m.setMinZoom(4);
    const high = m.cameraForBounds(offline ? BOUNDS : SWISS_BOUNDS, { padding: target.padding });
    // A new side: at least 90 degrees away from the last one.
    const side = ((lastSide.current ?? Math.random() * 360) + 90 + Math.random() * 180) % 360;
    lastSide.current = side;
    const rad = (side * Math.PI) / 180;
    const k = offline ? 0.25 : 1; // offline the canton is the whole world: stay close
    const highCenter: [number, number] = [
      target.center[0] + Math.sin(rad) * RISE_OFFSET_DEG * k / Math.cos((target.center[1] * Math.PI) / 180),
      target.center[1] + Math.cos(rad) * RISE_OFFSET_DEG * k,
    ];
    const turn = between(DIVE_BEARING) * (Math.random() < 0.5 ? -1 : 1);
    showBeacon(m, p);
    const up = await leg(m, id, () =>
      m.easeTo({ center: highCenter, zoom: high?.zoom ?? 7, pitch: 0, bearing: 0, padding: target.padding,
                 duration: RISE_MS, easing: easeOut, essential: true }));
    if (!up) return;
    await wait(HOLD_MS);
    if (flight.current !== id) return;
    const down = await leg(m, id, () =>
      m.flyTo({ ...target, pitch: between(DIVE_PITCH), bearing: turn, duration: DIVE_MS, curve: 1.3, easing: easeInOut,
                essential: true }));
    if (!down) return;
    beacon.current?.remove();
    beacon.current = null;
    const flat = await leg(m, id, () => m.easeTo({ pitch: 0, bearing: 0, duration: SETTLE_MS, easing: easeOut, essential: true }));
    if (!flat) return;
    endFlight(m);
    placePin(m, state.current.selected, true);
  }

  /**
   * A red map pin on the selected place (Timo, 24.10.): the ring alone is easy to miss on the colour map.
   * HTML marker, tip on the spot; a new element per selection replays the drop.
   */
  function placePin(m: maplibregl.Map, placeId: number | null, drop: boolean) {
    const p = placeId === null ? undefined : latest.current.places.find((x) => x.id === placeId);
    if (!p) {
      pin.current?.remove();
      pin.current = null;
      return;
    }
    if (pin.current && !drop) {
      pin.current.setLngLat([p.lon, p.lat]);
      return;
    }
    pin.current?.remove();
    const el = document.createElement("div");
    el.className = "desk-pin";
    el.innerHTML =
      '<svg width="26" height="34" viewBox="0 0 24 32" aria-hidden="true">' +
      '<path d="M12 1C6.2 1 1.5 5.6 1.5 11.4 1.5 19 12 31 12 31s10.5-12 10.5-19.6C22.5 5.6 17.8 1 12 1z" ' +
      `fill="${token("--accent", "#e2001a")}" stroke="#fff" stroke-width="1.5"/>` +
      '<circle cx="12" cy="11.5" r="4" fill="#fff"/></svg>';
    pin.current = new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat([p.lon, p.lat]).addTo(m);
  }

  /** Karte | Luftbild: show one background layer. Before the style has loaded, the load handler applies it. */
  function applyBasemap(m: maplibregl.Map) {
    try {
      const b = latest.current.basemap;
      m.setLayoutProperty("base", "visibility", b === "karte" ? "visible" : "none");
      m.setLayoutProperty("aerial", "visibility", b === "luftbild" ? "visible" : "none");
    } catch {
      // Style still loading.
    }
  }

  useEffect(() => {
    if (map.current) applyBasemap(map.current);
  }, [basemap]);

  /** The selected place's uncertainty circle; none without a selection or radius. */
  function drawCircle(m: maplibregl.Map) {
    const id = state.current.selected;
    const p = id === null ? undefined : latest.current.places.find((x) => x.id === id);
    (m.getSource("uncertainty") as maplibregl.GeoJSONSource | undefined)?.setData(p && p.radius_m > 0 ? circleData(p) : NO_CIRCLE);
  }

  // Data changes (results arrive, reviews change the classes).
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    (m.getSource("places") as maplibregl.GeoJSONSource | undefined)?.setData(placesData(places));
    applyState(m);
    drawCounts(m);
    placePin(m, state.current.selected, false);
    drawCircle(m);
  }, [places]);

  useEffect(() => {
    const m = map.current;
    const prevSelected = state.current.selected;
    state.current = { hovered: hoveredPlace, selected: selectedPlace };
    if (!m) return;
    applyState(m);
    if (selectedPlace !== prevSelected) {
      if (reducedMotion() || selectedPlace === null) placePin(m, selectedPlace, true);
      else placePin(m, null, false); // the pin drops in when the flight lands
      drawCircle(m);
    }
    // Fly to a newly selected place (jumpTo under reduced motion), zoomed out as far as its circle needs.
    // The flight first rises to the canton overview, then comes down on the place (Said, 24.10.).
    if (selectedPlace !== null && selectedPlace !== prevSelected) {
      const p = latest.current.places.find((x) => x.id === selectedPlace);
      if (p) {
        const pad = framePadding();
        const fit =
          p.radius_m > 0
            ? m.cameraForBounds(circleBox(p), {
                padding: { top: pad.top + 40, right: pad.right + 40, bottom: pad.bottom + 40, left: pad.left + 40 },
              })?.zoom
            : undefined;
        // Close in on the place; a wide uncertainty circle may pull it back out, but never below PICK_FLOOR.
        const zoom = Math.max(Math.min(PICK_ZOOM, fit ?? Infinity), PICK_FLOOR);
        const target = { center: [p.lon, p.lat] as [number, number], zoom, padding: pad };
        if (reducedMotion()) m.jumpTo(target);
        else void fly(m, p, target);
      }
    }
  }, [hoveredPlace, selectedPlace]);

  return (
    <div role="region" aria-label="Karte der Fotostandorte" className="relative h-full w-full">
      <div ref={container} className="h-full w-full" />
      <p className="pointer-events-none absolute bottom-0 right-0 bg-paper px-1.5 py-0.5 text-meta text-ink-muted">
        © swisstopo{offline ? "" : " · Sentinel-2 cloudless by EOX (Copernicus Sentinel data 2020)"}
      </p>
    </div>
  );
}
