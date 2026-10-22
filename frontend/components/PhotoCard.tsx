import Link from "next/link";
import { imageUrl } from "@/lib/api";
import { analyseHref, metaLine, photoTitle } from "@/lib/format";
import type { PhotoRecord } from "@/lib/types";

export default function PhotoCard({ record }: { record: PhotoRecord }) {
  return (
    <Link href={analyseHref(record.id)} className="group block fade-in">
      <figure>
        <div className="flex aspect-[3/2] items-center justify-center bg-paper-2 p-3 transition-colors duration-fade group-hover:bg-rule">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageUrl(record.id, 480)}
            alt={photoTitle(record)}
            loading="lazy"
            className="max-h-full max-w-full object-contain"
          />
        </div>
        <figcaption className="mt-2">
          <p className="text-sm font-medium group-hover:text-accent">{photoTitle(record)}</p>
          <p className="mt-0.5 font-mono text-meta text-ink-muted">{metaLine(record)}</p>
        </figcaption>
      </figure>
    </Link>
  );
}
