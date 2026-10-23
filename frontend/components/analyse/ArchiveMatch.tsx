"use client";

// "Das Archiv kennt diesen Ort" (FRONTPAGE_PLAN 5): the photo beside the archive's own reference photo of
// the same place, from the best similar_image evidence. Renders nothing when there is no match.
// "verifiziert" only when Said marks the match LightGlue-verified (FRONTPAGE_PLAN 9).
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

function Figure({ record, caption, href }: { record: PhotoRecord; caption: string; href?: string | null }) {
  const img = (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={imageUrl(record.id, 800)} alt={record.title ?? record.signature ?? record.id} className="h-48 w-full object-contain" />
  );
  return (
    <figure className="min-w-0">
      <div className="bg-paper-2 p-2">
        {href ? (
          <a href={href} target="_blank" rel="noreferrer" title="Im Katalog ansehen">
            {img}
          </a>
        ) : (
          img
        )}
      </div>
      <figcaption className="mt-1.5 font-mono text-meta text-ink-muted">{caption}</figcaption>
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
    <section className="fade-in mt-8">
      <h2 className="text-h3">Das Archiv kennt diesen Ort</h2>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Figure record={record} caption={`${yearOf(record)} · ${record.signature ?? record.id}`} />
        <Figure
          record={ref}
          caption={[yearOf(ref), ref.signature ?? ref.id, SOURCE_LABELS[ref.source] ?? ref.source].join(" · ")}
          href={ref.source_url}
        />
      </div>
      <p className="mt-2 text-small text-ink-muted">
        {meta}
        {match.evidence.summary && <span>. {match.evidence.summary}</span>}
      </p>
      {ref.source_url && (
        <a href={ref.source_url} target="_blank" rel="noreferrer" className="link text-small">
          Referenzfoto im Katalog
        </a>
      )}
    </section>
  );
}
