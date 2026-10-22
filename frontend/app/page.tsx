"use client";

// Archiv (build step 2): demo cards first in pitch order, then the showcase, undated before dated.
import { useCallback, useEffect, useState } from "react";
import PhotoCard from "@/components/PhotoCard";
import { getDemo, listPhotos } from "@/lib/api";
import { isUndated } from "@/lib/format";
import type { PhotoRecord } from "@/lib/types";

const PAGE_SIZE = 48;

function order(demo: PhotoRecord[], showcase: PhotoRecord[]): PhotoRecord[] {
  const demoIds = new Set(demo.map((r) => r.id));
  const rest = showcase.filter((r) => !demoIds.has(r.id));
  // Stable sort keeps the backend order inside each group.
  const sorted = [...rest].sort((a, b) => Number(isUndated(b)) - Number(isUndated(a)));
  return [...demo, ...sorted];
}

export default function ArchivPage() {
  const [demo, setDemo] = useState<PhotoRecord[]>([]);
  const [showcase, setShowcase] = useState<PhotoRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMore = useCallback(async (offset: number) => {
    setLoading(true);
    try {
      const page = await listPhotos({ split: "showcase", limit: PAGE_SIZE, offset });
      setShowcase((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
      setTotal(page.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    getDemo()
      .then((items) => setDemo(items.map((d) => d.record)))
      .catch(() => setDemo([])); // the grid still works from /photos alone
    loadMore(0);
  }, [loadMore]);

  const cards = order(demo, showcase);
  const undated = cards.filter(isUndated).length;

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-8 md:px-8">
      <div className="mb-6 border-b border-rule pb-4">
        <h1 className="font-serif text-page">Archiv</h1>
        <p className="mt-1 text-meta text-ink-muted">
          {cards.length > 0
            ? `${cards.length} von ${Math.max(total, cards.length)} Karten · ${undated} ohne Datum`
            : "Ansichtskarten und Flugaufnahmen aus dem Staatsarchiv Schwyz"}
        </p>
      </div>

      {error && <p className="text-bad">Archiv konnte nicht geladen werden: {error}</p>}
      {!error && loading && cards.length === 0 && <p className="text-ink-muted">Lade Archiv ...</p>}
      {!error && !loading && cards.length === 0 && <p className="text-ink-muted">Keine Karten gefunden.</p>}

      <div className="grid grid-cols-1 gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {cards.map((r) => (
          <PhotoCard key={r.id} record={r} />
        ))}
      </div>

      {showcase.length < total && (
        <div className="mt-10 flex justify-center">
          <button
            type="button"
            onClick={() => loadMore(showcase.length)}
            disabled={loading}
            className="rounded border border-rule px-4 py-2 text-body hover:border-ink disabled:text-ink-muted"
          >
            {loading ? "Lade ..." : "Weitere Karten laden"}
          </button>
        </div>
      )}
    </main>
  );
}
