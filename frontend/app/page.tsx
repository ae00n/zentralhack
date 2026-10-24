"use client";

// Arbeitsplatz (FRONTPAGE_PLAN 4): the whole SG.CIV.17 set after the agent processed it. Counters band,
// Excel button, and the photo list (Prio 1 | Alle, 4 sorts, filter via counters, search from the header).
// FRONTPAGE_POLISH 5: one viewport, the map fills it and the list floats on the left as a 400px panel.
// Hover and selection are synced both ways (FRONTPAGE_PLAN 4, Behaviour).
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import DeskBand from "@/components/desk/DeskBand";
import { FOCUS_RING } from "@/components/ui/button";
import Segmented from "@/components/ui/Segmented";
import Select from "@/components/ui/Select";
import PhotoDetail from "@/components/desk/PhotoDetail";
import PhotoRow, { rowId } from "@/components/desk/PhotoRow";
import { errorText, exportXlsxUrl, getTilesUrl, listChallenge, listResults, tileTemplate } from "@/lib/api";
import {
  FILTERS,
  SORTS,
  aggregatePlaces,
  certClass,
  countItems,
  filterItems,
  searchItems,
  sortItems,
  yearSpan,
  type DeskItem,
  type FilterKey,
  type SortKey,
} from "@/lib/desk";
import { journeyOf } from "@/lib/journey";
import { useReviewStore, withLocalReview } from "@/lib/reviewQueue";
import { cn } from "@/lib/cn";
import { analyseHref } from "@/lib/format";
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
  const [sort, setSort] = useState<SortKey>("unsure");
  const [filter, setFilter] = useState<FilterKey>("all");
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
  const shown = sortItems(filterItems(searchItems(items, q), filter), sort);
  // The map shows what the list shows (scope, search, filter).
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
  const backToList = () => {
    const id = selected;
    setSelected(null);
    if (fotoParam) router.replace(q ? `/?q=${encodeURIComponent(q)}` : "/", { scroll: false });
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

      <main className="relative lg:h-[calc(100vh-54px)] lg:overflow-hidden">
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
                journey={journeyOf(selectedItem?.result ?? null)}
              />
            )}
          </div>
          {/* Aerial photo | map, top right next to the zoom buttons (MapLibre control: 10 px margin, 29 px wide). */}
          <Segmented
            label="Hintergrund"
            value={basemap}
            onChange={pickBasemap}
            options={[
              { key: "luftbild", label: "Luftbild" },
              { key: "karte", label: "Karte" },
            ]}
            className="absolute right-12 top-2.5 z-10 border border-rule/[0.08] bg-paper-2/90 shadow-panel backdrop-blur"
          />
          {/* Legend: a small floating card, centred in the free map area right of the panel. */}
          <div className="absolute bottom-3 left-1/2 z-10 flex h-8 max-w-[calc(100%-24px)] -translate-x-1/2 items-center gap-3 overflow-x-auto whitespace-nowrap rounded border border-rule/[0.08] bg-paper/90 px-2.5 text-meta text-ink-muted backdrop-blur lg:left-[calc(50%+206px)]">
            {LEGEND.map((l) => (
              <span key={l.cls} className="inline-flex items-center gap-1.5">
                <span className={`cert-dot cert-dot-${l.cls}`} aria-hidden />
                {l.label}
              </span>
            ))}
            {withoutPlace > 0 && (
              <button
                type="button"
                onClick={() => setFilter("noplace")}
                className={cn("rounded-sm underline decoration-rule/20 underline-offset-2 hover:text-ink", FOCUS_RING)}
              >
                {withoutPlace === 1 ? "1 Foto ohne Ort" : `${withoutPlace} Fotos ohne Ort`}
              </button>
            )}
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
            filter={filter}
            onFilter={setFilter}
            excelUrl={exportXlsxUrl({ split: "challenge", priority: scope === "prio1" ? 1 : undefined })}
          />

          <div className="flex flex-wrap items-center gap-2 border-b border-rule/[0.08] px-3 py-2">
            <Segmented
              label="Umfang"
              value={scope}
              onChange={setScope}
              options={[
                { key: "prio1", label: "Prio 1" },
                { key: "all", label: `Alle ${records?.length ?? ""}`.trim() },
              ]}
            />
            <Select label="Sortierung" value={sort} onChange={setSort} options={SORTS} />
            <Select label="Filter" prefix value={filter} onChange={setFilter} options={FILTERS} />
          </div>

          <p className="px-3 pt-2 text-meta tnum text-ink-muted" aria-live="polite">
            {shown.length} von {items.length} Fotos
            {q && (
              <>
                {" · "}Suche «{q}»{" · "}
                <a href="/" className="underline decoration-rule/20 underline-offset-2 hover:text-ink">
                  zurücksetzen
                </a>
              </>
            )}
            {loadingResults && " · lade Ergebnisse ..."}
          </p>
          {error && <p className="px-3 pt-2 text-ui text-bad">Server nicht erreichbar oder Fehler: {error}</p>}

          {records && shown.length === 0 ? (
            <p className="py-10 text-center text-ui text-ink-muted">Keine Fotos für diese Auswahl.</p>
          ) : (
            <ul className="mt-1 min-h-0 flex-1 overflow-y-auto">
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
