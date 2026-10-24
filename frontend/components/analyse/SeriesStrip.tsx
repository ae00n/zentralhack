"use client";

// Fotoserie, light version (FRONTPAGE_PLAN 5): the session siblings from raw.session (same camera, under
// 30 min apart, usually the same place) as a thumbnail strip of links. Propagation ("S") is cut first.
import Link from "next/link";
import { useEffect, useState } from "react";
import { getPhoto, imageUrl } from "@/lib/api";
import { analyseHref } from "@/lib/format";
import type { PhotoRecord } from "@/lib/types";

/** "challenge:SG.CIV.17.408" → "SG.CIV.17.408" when the sibling's record is not available. */
function signatureOf(id: string, record: PhotoRecord | null | undefined): string {
  return record?.signature ?? id.replace(/^[a-z]+:/, "");
}

export default function SeriesStrip({ record }: { record: PhotoRecord }) {
  const siblings = record.raw?.session ?? [];
  const [records, setRecords] = useState<Map<string, PhotoRecord | null>>(new Map());

  useEffect(() => {
    let stale = false;
    Promise.all(siblings.map((id) => getPhoto(id).catch(() => null))).then(
      (rs) => !stale && setRecords(new Map(siblings.map((id, i) => [id, rs[i]]))),
    );
    return () => {
      stale = true;
    };
  }, [record.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (siblings.length === 0) return null;
  return (
    <section aria-label="Fotoserie">
      <p className="text-ui">
        <span className="font-semibold">Fotoserie:</span>{" "}
        {siblings.length === 1 ? "1 weiteres Foto dieser Serie" : `${siblings.length} weitere Fotos dieser Serie`}
      </p>
      <ol className="mt-2 flex gap-2 overflow-x-auto pb-1">
        {siblings.map((id) => {
          const sig = signatureOf(id, records.get(id));
          return (
            <li key={id} className="shrink-0">
              <Link href={analyseHref(id)} className="group block" title={`${sig} ansehen`}>
                <span className="flex h-14 w-24 items-center justify-center bg-paper-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imageUrl(id, 120)} alt="" loading="lazy" className="max-h-full max-w-full object-contain" />
                </span>
                <span className="mt-0.5 block font-mono text-[11px] text-ink-muted group-hover:text-ink-strong group-hover:underline">
                  {sig}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
