import { imageUrl } from "@/lib/api";
import type { PhotoRecord } from "@/lib/types";

// The photo on the stage (FRONTPAGE_POLISH 6): uncropped on the canvas with 32 px air, no mat, no border,
// no rounding. One caption line: mono signature, then date, camera and source in Inter tnum.
export default function PhotoPanel({ record }: { record: PhotoRecord }) {
  const camera = record.raw?.exif?.model;
  const source = record.license?.credit?.split(",")[0];
  const facts = [record.date?.raw?.trim() || "keine Angabe", camera, source].filter(Boolean);
  return (
    <figure className="flex h-full flex-col p-4 lg:p-8 lg:pb-4">
      <div className="flex min-h-0 flex-1 items-center justify-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl(record.id, 1024)}
          alt={record.title ?? record.signature ?? record.id}
          className="max-h-[60vh] max-w-full object-contain lg:max-h-full"
        />
      </div>
      <figcaption className="mt-3 text-meta tnum text-ink-muted">
        {record.title && <span className="mr-1 text-ink">{record.title} ·</span>}
        <span className="font-mono text-ink">{record.signature ?? record.id}</span>
        {facts.map((f) => ` · ${f}`).join("")}
      </figcaption>
    </figure>
  );
}
