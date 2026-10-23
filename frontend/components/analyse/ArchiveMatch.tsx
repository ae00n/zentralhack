"use client";

// "Das Archiv kennt diesen Ort", the stage's Vergleich tab (FRONTPAGE_POLISH 6): the photo beside the
// archive's reference photo of the same place, equal height, the years big above each image. Data from
// the best similar_image evidence; renders nothing when there is no match. "verifiziert" only when Said
// marks the match LightGlue-verified (FRONTPAGE_PLAN 9).
import { useEffect, useState } from "react";
import { bestReferenceMatch, getPhoto, imageUrl } from "@/lib/api";
import type { AnalysisResult, PhotoRecord } from "@/lib/types";

const SOURCE_LABELS: Record<string, string> = {
  staatsarchiv: "Staatsarchiv Schwyz",
  epics: "ETH-Bibliothek Zürich",
  smapshot: "Smapshot",
  lubis: "swisstopo LUBIS",
  nb: "Nationalbibliothek",
  challenge: "Staatsarchiv Schwyz",
};

/** "2005", or the catalogue's own wording for a range ("vor 13.6.1907"), or "keine Angabe". */
function yearOf(r: PhotoRecord): string {
  const d = r.date;
  if (d?.year_from && d.year_from === d.year_to) return String(d.year_from);
  return d?.raw?.trim() || "keine Angabe";
}

function Figure({ record, href }: { record: PhotoRecord; href?: string | null }) {
  const img = (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={imageUrl(record.id, 1024)}
      alt={record.title ?? record.signature ?? record.id}
      className="h-full max-h-[40vh] w-full object-contain lg:max-h-none"
    />
  );
  return (
    <figure className="flex min-h-0 min-w-0 flex-col">
      <p className="text-hero tnum text-ink">{yearOf(record)}</p>
      <div className="mt-3 min-h-0 flex-1">
        {href ? (
          <a href={href} target="_blank" rel="noreferrer" title="Im Katalog ansehen" className="block h-full">
            {img}
          </a>
        ) : (
          img
        )}
      </div>
      <figcaption className="mt-2 text-meta text-ink-muted">
        <span className="font-mono text-ink">{record.signature ?? record.id}</span> ·{" "}
        {SOURCE_LABELS[record.source] ?? record.source}
      </figcaption>
    </figure>
  );
}

export default function ArchiveMatch({ record, result }: { record: PhotoRecord; result: AnalysisResult }) {
  const match = bestReferenceMatch(result);
  const refId = match?.evidence.ref_id ?? null;
  const [ref, setRef] = useState<PhotoRecord | null>(null);

  useEffect(() => {
    setRef(null);
    if (!refId) return;
    let stale = false;
    getPhoto(refId)
      .then((r) => !stale && setRef(r))
      .catch(() => !stale && setRef(null)); // reference record missing: show nothing rather than a broken box
    return () => {
      stale = true;
    };
  }, [refId]);

  if (!match || !ref) return null;
  const inliers = match.evidence.inliers;
  const meta = match.verified
    ? ["Bildabgleich verifiziert", inliers ? `${inliers} übereinstimmende Punkte` : null].filter(Boolean).join(" · ")
    : "ähnliches Referenzfoto";

  return (
    <section aria-label="Das Archiv kennt diesen Ort" className="flex h-full flex-col p-4 lg:p-8">
      <p className="text-meta font-medium uppercase tracking-[0.06em] text-ink-muted">Das Archiv kennt diesen Ort</p>
      <div className="mt-4 grid min-h-0 flex-1 grid-cols-2 gap-6">
        <Figure record={record} />
        <Figure record={ref} href={ref.source_url} />
      </div>
      <p className="mt-4 text-ui text-ink-muted">
        <span className="text-ink">{meta}</span>
        {match.evidence.summary && <span>. {match.evidence.summary}</span>}
        {ref.source_url && (
          <>
            {" · "}
            <a href={ref.source_url} target="_blank" rel="noreferrer" className="link">
              Referenzfoto im Katalog
            </a>
          </>
        )}
      </p>
    </section>
  );
}
