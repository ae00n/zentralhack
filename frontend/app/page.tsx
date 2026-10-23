"use client";

// Arbeitsplatz (FRONTPAGE_PLAN 4): the whole SG.CIV.17 set after the agent processed it. Counters band,
// Excel button, and the photo list (Prio 1 | Alle, 4 sorts, filter via counters, search from the red band).
// The desk map (left column) comes with build item 6.
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import DeskBand from "@/components/desk/DeskBand";
import PhotoRow from "@/components/desk/PhotoRow";
import { errorText, exportXlsxUrl, listChallenge, listResults } from "@/lib/api";
import {
  FILTERS,
  SORTS,
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
import type { AnalysisResult, PhotoRecord } from "@/lib/types";

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

      <main className="wrapper py-6">
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
            <PhotoRow key={item.record.id} item={item} />
          ))}
        </ul>
      </main>
    </>
  );
}
