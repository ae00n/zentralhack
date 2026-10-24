"use client";

// Arbeitsplatz (FRONTPAGE_PLAN 4): the whole SG.CIV.17 set after the agent processed it. Counters band,
// Excel button, and the photo list (Prio 1 | Alle, 4 sorts, search in the panel; no filters since the
// sidebar makeover, Said 24.10.).
// FRONTPAGE_POLISH 5: one viewport, the map fills it and the list floats on the left as a 400px panel.
// Hover and selection are synced both ways (FRONTPAGE_PLAN 4, Behaviour).
// UPLOAD_PLAN step 2b: the main page again (/), also shown at /stapel/challenge.
import dynamic from "next/dynamic";
import { PersonStanding } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type CSSProperties } from "react";
import DeskBand from "@/components/desk/DeskBand";
import DeskSearch from "@/components/desk/DeskSearch";
import { FOCUS_RING } from "@/components/ui/button";
import Segmented from "@/components/ui/Segmented";
import Select from "@/components/ui/Select";
import PhotoDetail from "@/components/desk/PhotoDetail";
import PhotoRow, { rowId } from "@/components/desk/PhotoRow";
import StreetPane from "@/components/desk/StreetPane";
import { errorText, exportXlsxUrl, getTilesUrl, listChallenge, listResults, tileTemplate } from "@/lib/api";
import {
  SORTS,
  aggregatePlaces,
  certClass,
  countItems,
  searchItems,
  sortItems,
  yearSpan,
  type DeskItem,
  type SortKey,
} from "@/lib/desk";
import { reasoningOf } from "@/lib/reasoning";
import { nearestStreetView, type StreetSpot } from "@/lib/streetview";
import { useReviewStore, withLocalReview } from "@/lib/reviewQueue";
import { cn } from "@/lib/cn";
import { analyseHref, deskHref } from "@/lib/format";
import type { AnalysisResult, PhotoRecord } from "@/lib/types";

const DeskMap = dynamic(() => import("@/components/desk/DeskMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-paper-2" />,
});

const LEGEND: { cls: string; label: string }[] = [
  { cls: "confirmed", label: "bestätigt" },
  { cls: "sure", label: "sicher" },
  { cls: "check", label: "Prüfung nötig" },
  { cls: "open", label: "nicht bestimmbar" },
];

type Scope = "prio1" | "all";
type Basemap = "karte" | "luftbild";
const BASEMAP_KEY = "desk-basemap";

export default function ArbeitsplatzPage() {
  // useSearchParams needs a Suspense boundary for the static build.
  return (
    <Suspense fallback={<p className="wrapper py-8 text-ink-muted">Lade Arbeitsplatz ...</p>}>
      <Arbeitsplatz />
    </Suspense>
  );
}

function Arbeitsplatz() {
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  // Back from the full view: "?foto=<id>" opens that photo in the side panel again.
  const fotoParam = params.get("foto");
  const [records, setRecords] = useState<PhotoRecord[] | null>(null);
  const [results, setResults] = useState<Map<string, AnalysisResult | null>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("prio1");
  const [sort, setSort] = useState<SortKey>("sure"); // most certain first (Said, 24.10.)
  const [loadingResults, setLoadingResults] = useState(false);
  useReviewStore(); // decisions made on the detail page count here at once
  const router = useRouter();
  const [tiles, setTiles] = useState<{ tilesUrl: string; offline: boolean } | null>(null);
  // Hover and selection by photo id; the map works on places (several photos can share one).
  const [hoveredPhoto, setHoveredPhoto] = useState<string | null>(null);
  const [hoveredPlace, setHoveredPlace] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // Phone: list and map are tabs, list first (plan 4). From lg both show side by side.
  const [view, setView] = useState<"list" | "map">("list");
  // Aerial photo | map (Timo, 24.10.), remembered per browser; the aerial photo is the default (Said, 24.10.).
  const [basemap, setBasemap] = useState<Basemap>("luftbild");

  useEffect(() => {
    getTilesUrl().then(setTiles);
    try {
      if (localStorage.getItem(BASEMAP_KEY) === "karte") setBasemap("karte");
    } catch {
      // No storage (private window): start on the aerial photo.
    }
  }, []);

  const pickBasemap = (b: Basemap) => {
    setBasemap(b);
    try {
      localStorage.setItem(BASEMAP_KEY, b);
    } catch {
      // Not remembered, still switched.
    }
  };

  // The desk never scrolls: drop the reserved scrollbar gutter (globals.css) so the map reaches the edge.
  useEffect(() => {
    const html = document.documentElement;
    html.style.scrollbarGutter = "auto";
    return () => {
      html.style.scrollbarGutter = "";
    };
  }, []);

  useEffect(() => {
    listChallenge()
      .then(setRecords)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    if (fotoParam && records?.some((r) => r.id === fotoParam)) setSelected(fotoParam);
  }, [fotoParam, records]);

  const prioRecords = useMemo(() => (records ?? []).filter((r) => r.raw?.priority === 1), [records]);
  const scoped = scope === "prio1" ? prioRecords : (records ?? []);

  // Results for the shown scope; Prio 1 first. listResults caches, so switching back is instant.
  useEffect(() => {
    if (!records) return;
    let stale = false;
    setLoadingResults(true);
    listResults(scoped.map((r) => r.id))
      .then((m) => !stale && setResults((prev) => new Map([...prev, ...m])))
      .catch((e: unknown) => !stale && setError(errorText(e)))
      .finally(() => !stale && setLoadingResults(false));
    return () => {
      stale = true;
    };
  }, [records, scope]); // eslint-disable-line react-hooks/exhaustive-deps

  const toItems = (rs: PhotoRecord[]): DeskItem[] => rs.map((record) => ({ record, result: withLocalReview(results.get(record.id) ?? null) }));
  const items = toItems(scoped);
  const counts = countItems(items);
  const prio = countItems(toItems(prioRecords));
  const shown = sortItems(searchItems(items, q), sort);
  // The map shows what the list shows (scope, search).
  // Keyed by content, not by the array: hover re-renders must not rebuild the map data (it resets feature-state).
  const placeKey = shown
    .map((i) => {
      const c = i.result?.fields.coordinates?.value;
      return `${i.record.id}:${certClass(i.result)}:${c ? `${c.lat},${c.lon},${c.radius_m}` : ""}`;
    })
    .join("|");
  const { places, placeOf, withoutPlace } = useMemo(() => aggregatePlaces(shown), [placeKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const placeOfHoveredPhoto = hoveredPhoto ? (placeOf.get(hoveredPhoto) ?? null) : null;
  const hoveredIds = new Set(places.find((p) => p.id === hoveredPlace)?.ids ?? []);
  const signatureOf = (id: string) => scoped.find((r) => r.id === id)?.signature ?? id;

  const select = (photoId: string) => {
    setSelected(photoId);
    // The row may be far down the list.
    setTimeout(() => document.getElementById(rowId(photoId))?.scrollIntoView({ block: "nearest" }), 0);
  };
  // Clicking a pin: the first click selects, a second click on the same photo opens it.
  const pickFromMap = (photoId: string) => {
    if (selected === photoId) return router.push(analyseHref(photoId));
    // On the phone the list is the other tab: show the picked row there.
    if (!window.matchMedia("(min-width: 1024px)").matches) setView("list");
    select(photoId);
  };

  // The side panel shows the picked photo instead of the list (Said, 24.10.); Escape goes back.
  const selectedItem = selected ? (items.find((i) => i.record.id === selected) ?? null) : null;
  // Its reasoning for the map (landmark lookups start now, the flight picks them up on the way down).
  const reasoningPromise = useMemo(() => (selectedItem ? reasoningOf(selectedItem.result) : null), [selected, Boolean(selectedItem?.result)]); // eslint-disable-line react-hooks/exhaustive-deps
  // Street view split on the right (Said, 24.10.): opens once the flight to the picked photo has landed, and
  // only when Google has Street View on the spot (15 m, checked during the flight); otherwise no pane at all.
  // A toggle next to the background switch turns it on; off by default, and nothing goes to Google while off.
  const [landed, setLanded] = useState<string | null>(null);
  const [streetOn, setStreetOn] = useState(false);
  const [paneW, setPaneW] = useState(0);
  const [pano, setPano] = useState<{ id: string; spot: StreetSpot } | null>(null);
  const spot = selectedItem?.result?.fields.coordinates?.value ?? null;
  useEffect(() => {
    if (!streetOn || !selected || !spot || tiles?.offline) return;
    let live = true;
    void nearestStreetView(spot.lat, spot.lon).then((s) => live && s && setPano({ id: selected, spot: s }));
    return () => {
      live = false;
    };
  }, [streetOn, selected, spot?.lat, spot?.lon, tiles?.offline]); // eslint-disable-line react-hooks/exhaustive-deps
  const streetSpot = pano && pano.id === selected ? pano.spot : null;
  const streetOpen = Boolean(selectedItem && spot && streetSpot && landed === selected && streetOn && paneW > 0 && !tiles?.offline);
  const onLanded = () => {
    setLanded(selected);
    // Wide screens only: about 42 % of the window, at most 760 px.
    setPaneW(window.matchMedia("(min-width: 1024px)").matches ? Math.round(Math.min(window.innerWidth * 0.42, 760)) : 0);
  };
  const backToList = () => {
    const id = selected;
    setSelected(null);
    if (fotoParam) router.replace(deskHref({ q }), { scroll: false });
    if (id) setTimeout(() => document.getElementById(rowId(id))?.scrollIntoView({ block: "nearest" }), 0);
  };
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !(e.target instanceof HTMLInputElement)) backToList();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const meta = records
    ? [`${records.length} Fotos`, `${prioRecords.length} Prio 1`, yearSpan(records)].filter(Boolean).join(" · ")
    : "Lade Fotos ...";

  return (
    <>
      {/* Phone: list and map are tabs, list first. From lg the map fills the page and the list floats. */}
      <div className="px-3 pt-3 lg:hidden">
        <Segmented
          role="tab"
          label="Ansicht"
          value={view}
          onChange={setView}
          options={[
            { key: "list", label: "Liste" },
            { key: "map", label: "Karte" },
          ]}
          className="w-full grid-cols-2"
        />
      </div>

      <main
        className={cn("relative lg:h-[calc(100vh-54px)] lg:overflow-hidden", streetOpen && "street-open")}
        style={{ "--pane-w": `${streetOpen ? paneW : 0}px` } as CSSProperties}
      >
        <div className={cn("relative h-[70vh] lg:absolute lg:inset-0 lg:block lg:h-auto", view === "map" ? "block" : "hidden")}>
          <div className="absolute inset-0 bg-canvas">
            {tiles && (
              <DeskMap
                places={places}
                // Colour map online; the offline tile bundle only has the grey one.
                tiles={tileTemplate(tiles.tilesUrl, tiles.offline ? "ch.swisstopo.pixelkarte-grau" : "ch.swisstopo.pixelkarte-farbe", "current")}
                grey={tiles.offline}
                // Offline only the demo areas have SWISSIMAGE tiles.
                aerialTiles={tileTemplate(tiles.tilesUrl, "ch.swisstopo.swissimage", "current")}
                basemap={basemap}
                offline={tiles.offline}
                hoveredPlace={hoveredPlace ?? placeOfHoveredPhoto}
                selectedPlace={selected ? (placeOf.get(selected) ?? null) : null}
                onHover={setHoveredPlace}
                onPickPhoto={pickFromMap}
                labelOf={signatureOf}
                panelWide={Boolean(selectedItem)}
                reasoning={reasoningPromise}
                onLanded={onLanded}
                unplaced={Boolean(selectedItem && !placeOf.has(selectedItem.record.id))}
                paneWidth={streetOpen ? paneW : 0}
              />
            )}
          </div>
          {streetOpen && selectedItem && spot && streetSpot && (
            <StreetPane
              key={selectedItem.record.id}
              lat={spot.lat}
              lon={spot.lon}
              pano={streetSpot}
              building={(() => {
                const b = selectedItem.result?.fields.buildings?.value;
                return Array.isArray(b) && typeof b[0] === "string" ? b[0] : null;
              })()}
              signature={selectedItem.record.signature ?? selectedItem.record.id}
              reasoning={reasoningPromise}
              width={paneW}
              onClose={() => setStreetOn(false)}
            />
          )}
          {/* Aerial photo | map, top right next to the zoom buttons (MapLibre control: 10 px margin, 29 px wide). */}
          <div
            className="absolute top-2.5 z-10 flex items-center gap-2 transition-[right] duration-500"
            style={{ right: "calc(var(--pane-w) + 48px)" }}
          >
            {!tiles?.offline && (
              <button
                type="button"
                aria-pressed={streetOn}
                onClick={() => setStreetOn((v) => !v)}
                title="Zeigt Google Street View, wenn ein Panorama direkt am Standort liegt"
                className={cn(
                  "hidden h-8 items-center gap-1.5 rounded border border-rule/[0.08] px-2.5 text-ui shadow-panel backdrop-blur transition-colors duration-hover lg:inline-flex",
                  FOCUS_RING,
                  streetOn ? "bg-paper font-medium text-ink" : "bg-paper-2/90 text-ink-muted hover:text-ink",
                )}
              >
                <PersonStanding className="size-4" aria-hidden />
                Strassenansicht
                <span aria-hidden className={cn("ml-0.5 size-1.5 rounded-dot", streetOn ? "bg-accent" : "bg-ink-muted/40")} />
              </button>
            )}
            <Segmented
              label="Hintergrund"
              value={basemap}
              onChange={pickBasemap}
              options={[
                { key: "luftbild", label: "Luftbild" },
                { key: "karte", label: "Karte" },
              ]}
              className="border border-rule/[0.08] bg-paper-2/90 shadow-panel backdrop-blur"
            />
          </div>
          {/* Legend: a small floating card, centred in the free map area right of the panel. */}
          <div className="absolute bottom-3 left-1/2 z-10 flex h-8 max-w-[calc(100%-24px)] -translate-x-1/2 items-center gap-3 overflow-x-auto whitespace-nowrap rounded border border-rule/[0.08] bg-paper/90 px-2.5 text-meta text-ink-muted backdrop-blur lg:left-[calc((100%_+_412px_-_var(--pane-w))_/_2)] lg:transition-[left] lg:duration-500">
            {LEGEND.map((l) => (
              <span key={l.cls} className="inline-flex items-center gap-1.5">
                <span className={`cert-dot cert-dot-${l.cls}`} aria-hidden />
                {l.label}
              </span>
            ))}
            {withoutPlace > 0 && <span>{withoutPlace === 1 ? "1 Foto ohne Ort" : `${withoutPlace} Fotos ohne Ort`}</span>}
          </div>
        </div>

        <div
          className={cn(
            "flex-col bg-paper lg:absolute lg:bottom-3 lg:left-3 lg:top-3 lg:z-10 lg:flex lg:overflow-hidden lg:rounded-lg lg:border lg:border-rule/[0.08] lg:shadow-panel",
            // Wider while a photo is open (Said, 24.10.), with a smooth change of width.
            "lg:transition-[width] lg:duration-500 lg:ease-[cubic-bezier(0.2,0.7,0.2,1)]",
            selectedItem ? "lg:w-[480px]" : "lg:w-[400px]",
            view === "list" ? "flex" : "hidden",
          )}
        >
          {selectedItem ? (
            <PhotoDetail key={selectedItem.record.id} item={selectedItem} onBack={backToList} />
          ) : (
          <>
          <DeskBand
            meta={meta}
            counts={counts}
            prio={prio}
            excelUrl={exportXlsxUrl({ split: "challenge", priority: scope === "prio1" ? 1 : undefined })}
          />

          <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
            <DeskSearch className="w-full" />
            <Segmented
              label="Umfang"
              value={scope}
              onChange={setScope}
              options={[
                { key: "prio1", label: "Prio 1" },
                { key: "all", label: `Alle ${records?.length ?? ""}`.trim() },
              ]}
            />
            <Select label="Sortierung" value={sort} onChange={setSort} options={SORTS} className="ml-auto" />
          </div>

          {/* Only while it says something: a search is on or results are still loading. */}
          {(q || loadingResults) && (
            <p className="px-4 pb-2 text-meta tnum text-ink-muted" aria-live="polite">
              {q ? (
                <>
                  {shown.length} von {items.length} Fotos · Suche «{q}» ·{" "}
                  <a href={deskHref()} className="underline decoration-rule/20 underline-offset-2 hover:text-ink">
                    zurücksetzen
                  </a>
                </>
              ) : (
                "Lade Ergebnisse ..."
              )}
            </p>
          )}
          {error && <p className="px-3 pt-2 text-ui text-bad">Server nicht erreichbar oder Fehler: {error}</p>}

          {records && shown.length === 0 ? (
            <p className="py-10 text-center text-ui text-ink-muted">Keine Fotos für diese Auswahl.</p>
          ) : (
            <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto border-t border-rule/[0.06] px-2 py-2">
              {shown.map((item) => (
                <PhotoRow
                  key={item.record.id}
                  item={item}
                  hovered={hoveredIds.has(item.record.id)}
                  selected={selected === item.record.id}
                  onHover={setHoveredPhoto}
                  onSelect={select}
                />
              ))}
            </ul>
          )}
          </>
          )}
        </div>
      </main>
    </>
  );
}
