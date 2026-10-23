"use client";

// Arbeitsplatz (FRONTPAGE_PLAN 4): the whole SG.CIV.17 set after the agent processed it. Counters band,
// Excel button, and the photo list (Prio 1 | Alle, 4 sorts, filter via counters, search from the red band).
// Map left (55 %), list right (45 %); hover and selection are synced both ways (plan 4, Behaviour).
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import DeskBand from "@/components/desk/DeskBand";
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
import { useReviewStore, withLocalReview } from "@/lib/reviewQueue";
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

export default function ArbeitsplatzPage() {
  // useSearchParams needs a Suspense boundary for the static build.
  return (
    <Suspense fallback={<p className="wrapper py-8 text-ink-muted">Lade Arbeitsplatz ...</p>}>
      <Arbeitsplatz />
    </Suspense>
  );
}

function Arbeitsplatz() {
  const q = useSearchParams().get("q") ?? "";
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

  useEffect(() => {
    getTilesUrl().then(setTiles);
  }, []);

  useEffect(() => {
    listChallenge()
      .then(setRecords)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

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
      return `${i.record.id}:${certClass(i.result)}:${c ? `${c.lat},${c.lon}` : ""}`;
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

  const meta = records
    ? [`${records.length} Fotos`, `${prioRecords.length} Prio 1`, yearSpan(records)].filter(Boolean).join(" · ")
    : "Lade Fotos ...";

  return (
    <>
      <DeskBand
        meta={meta}
        counts={counts}
        prio={prio}
        filter={filter}
        onFilter={setFilter}
        excelUrl={exportXlsxUrl({ split: "challenge", priority: scope === "prio1" ? 1 : undefined })}
      />

      <div className="wrapper pt-4 lg:hidden">
        <div role="tablist" aria-label="Ansicht" className="flex rounded border border-ink-muted">
          {(
            [
              ["list", "Liste"],
              ["map", "Karte"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => setView(key)}
              className={`flex-1 py-2 text-small font-bold transition-colors duration-fade ${view === key ? "bg-ink text-white" : "text-ink-muted"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <main className="wrapper grid gap-8 py-6 lg:grid-cols-[minmax(0,55fr)_minmax(0,45fr)]">
        <div className={`lg:sticky lg:top-4 lg:block lg:self-start ${view === "map" ? "" : "hidden"}`}>
          <div className="h-[70vh] bg-paper-2 lg:h-[calc(100vh-120px)]">
            {tiles && (
              <DeskMap
                places={places}
                tiles={tileTemplate(tiles.tilesUrl, "ch.swisstopo.pixelkarte-grau", "current")}
                offline={tiles.offline}
                hoveredPlace={hoveredPlace ?? placeOfHoveredPhoto}
                selectedPlace={selected ? (placeOf.get(selected) ?? null) : null}
                onHover={setHoveredPlace}
                onPickPhoto={pickFromMap}
                labelOf={signatureOf}
              />
            )}
          </div>
          <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-ink-muted">
            <span>Legende:</span>
            {LEGEND.map((l) => (
              <span key={l.cls} className="inline-flex items-center gap-1.5">
                <span className={`cert-dot cert-dot-${l.cls}`} aria-hidden />
                {l.label}
              </span>
            ))}
            {withoutPlace > 0 && (
              <button type="button" onClick={() => setFilter("noplace")} className="underline hover:text-ink-strong">
                {withoutPlace === 1 ? "1 Foto ohne Ort" : `${withoutPlace} Fotos ohne Ort`}
              </button>
            )}
          </p>
        </div>

        <div className={`min-w-0 lg:block ${view === "list" ? "" : "hidden"}`}>
        {error && <p className="mb-4 text-bad">Server nicht erreichbar oder Fehler: {error}</p>}

        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-rule pb-3">
          <div role="group" aria-label="Umfang" className="inline-flex rounded border border-ink-muted">
            {(
              [
                ["prio1", "Prio 1"],
                ["all", `Alle ${records?.length ?? ""}`.trim()],
              ] as [Scope, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setScope(key)}
                aria-pressed={scope === key}
                className={`px-3 py-1.5 text-small font-bold transition-colors duration-fade ${scope === key ? "bg-ink text-white" : "text-ink-muted hover:text-ink-strong"}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4 text-small">
            <label className="flex items-center gap-2">
              <span className="text-ink-muted">Sortierung</span>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                className="rounded border border-ink-muted bg-paper px-2 py-1"
              >
                {SORTS.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2">
              <span className="text-ink-muted">Filter</span>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value as FilterKey)}
                className="rounded border border-ink-muted bg-paper px-2 py-1"
              >
                {FILTERS.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <p className="mt-3 text-small text-ink-muted" aria-live="polite">
          {shown.length} von {items.length} Fotos
          {q && (
            <>
              {" · "}Suche «{q}»{" · "}
              <a href="/" className="underline hover:text-ink-strong">
                zurücksetzen
              </a>
            </>
          )}
          {loadingResults && " · lade Ergebnisse ..."}
        </p>

        {records && shown.length === 0 && <p className="mt-6 text-ink-muted">Keine Fotos für diese Auswahl.</p>}
        <ul className="mt-2">
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
        </div>
      </main>
    </>
  );
}
