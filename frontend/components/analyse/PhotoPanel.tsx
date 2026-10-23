import { imageUrl } from "@/lib/api";
import { metaLine } from "@/lib/format";
import type { PhotoRecord } from "@/lib/types";

// The photo on a paper-2 mat. Caption in mono: "SG.CIV.17.3 · Aufnahmedatum 24.02.2005 · NIKON D1X",
// then the archive credit. Challenge photos have no title; that is what the Erschliessung proposes.
export default function PhotoPanel({ record }: { record: PhotoRecord }) {
  const camera = record.raw?.exif?.model;
  return (
    <figure>
      <div className="flex items-center justify-center bg-paper-2 p-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl(record.id, 1024)}
          alt={record.title ?? record.signature ?? record.id}
          className="max-h-[60vh] max-w-full object-contain"
        />
      </div>
      <figcaption className="mt-2">
        {record.title && <p className="text-h3">{record.title}</p>}
        <p className="font-mono text-meta text-ink-muted">{[metaLine(record), camera].filter(Boolean).join(" · ")}</p>
        {record.license && <p className="mt-0.5 text-meta text-ink-muted">{record.license.credit}</p>}
      </figcaption>
    </figure>
  );
}
