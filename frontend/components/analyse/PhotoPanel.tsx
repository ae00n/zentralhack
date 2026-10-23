import { imageUrl } from "@/lib/api";
import { metaLine, photoTitle } from "@/lib/format";
import type { PhotoRecord } from "@/lib/types";

export default function PhotoPanel({ record }: { record: PhotoRecord }) {
  return (
    <figure>
      <div className="flex items-center justify-center bg-paper-2 p-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl(record.id, 1024)} alt={photoTitle(record)} className="max-h-[48vh] max-w-full object-contain" />
      </div>
      <figcaption className="mt-2">
        <p className="text-h3">{photoTitle(record)}</p>
        <p className="mt-0.5 font-mono text-meta text-ink-muted">{metaLine(record)}</p>
        {record.license && <p className="mt-0.5 text-meta text-ink-muted">{record.license.credit}</p>}
      </figcaption>
    </figure>
  );
}
