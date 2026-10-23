import Link from "next/link";
import { imageUrl } from "@/lib/api";
import { analyseHref, metaLine, photoTitle } from "@/lib/format";
import type { PhotoRecord } from "@/lib/types";

interface Props {
  record: PhotoRecord;
  /** Export selection on the Archiv (step 6). The checkbox sits beside the link, not inside it. */
  selected?: boolean;
  onToggle?: (id: string) => void;
}

export default function PhotoCard({ record, selected = false, onToggle }: Props) {
  const title = photoTitle(record);
  return (
    <div className="relative fade-in">
      <Link href={analyseHref(record.id)} className="group block">
        <figure>
          <div className="flex aspect-[3/2] items-center justify-center bg-paper-2 p-3 transition-colors duration-fade group-hover:bg-rule">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl(record.id, 480)}
              alt={title}
              loading="lazy"
              className="max-h-full max-w-full object-contain"
            />
          </div>
          <figcaption className="mt-2">
            <p className="text-body font-bold group-hover:text-ink-strong">{title}</p>
            <p className="mt-0.5 font-mono text-meta text-ink-muted">{metaLine(record)}</p>
          </figcaption>
        </figure>
      </Link>
      {onToggle && (
        <label
          className={`absolute left-1.5 top-1.5 flex cursor-pointer items-center rounded border border-rule bg-paper p-1 ${selected ? "" : "opacity-70 hover:opacity-100"}`}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggle(record.id)}
            aria-label={`${title} für den Export auswählen`}
            className="h-3.5 w-3.5 cursor-pointer accent-[var(--accent)]"
          />
        </label>
      )}
    </div>
  );
}
