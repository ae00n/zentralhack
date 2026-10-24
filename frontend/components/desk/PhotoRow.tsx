import Link from "next/link";
import { FOCUS_RING } from "@/components/ui/button";
import { imageUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { certClass, modelClass, type DeskItem } from "@/lib/desk";
import { NOT_DETERMINED, analyseHref, formatPct, isEmptyValue } from "@/lib/format";
import { effectiveValue, formatValue } from "@/lib/review";

// List row. Sidebar makeover (Said, 24.10.): a large thumbnail, the building as the headline, place and
// street underneath, signature and certainty on a quiet top line. No dividers; rows are soft cards.
// Behaviour as before: hover highlights the pin, the first click selects (map flies there), a second
// click or Enter opens the detail page.

function lines(item: DeskItem): { headline: string; sub: string | null; status: string | null; warn: boolean } {
  const { result } = item;
  if (!result) return { headline: "Noch kein Ergebnis", sub: null, status: null, warn: false };
  const first = (v: ReturnType<typeof effectiveValue>) => (Array.isArray(v) ? v[0] : v);
  const place = effectiveValue(result, "locality") ?? effectiveValue(result, "municipality");
  const building = first(effectiveValue(result, "buildings"));
  const street = effectiveValue(result, "street");
  const placeText = isEmptyValue(place) ? null : formatValue(place);
  const sub = [building ? placeText : null, isEmptyValue(street) ? null : formatValue(street)].filter(Boolean).join(" · ");
  const review = result.review?.status;
  const status =
    review === "bestaetigt" ? "bestätigt" : review === "korrigiert" ? "korrigiert" : modelClass(result) === "sure" ? "sicher" : "Prüfung nötig";
  return {
    headline: building ?? placeText ?? NOT_DETERMINED,
    sub: sub || null,
    status,
    warn: status === "Prüfung nötig",
  };
}

/** DOM id of a row, for scrollIntoView when the map selects it. */
export function rowId(photoId: string): string {
  return `row-${photoId.replace(/[^\w-]/g, "-")}`;
}

interface Props {
  item: DeskItem;
  hovered?: boolean;
  selected?: boolean;
  onHover?: (photoId: string | null) => void;
  onSelect?: (photoId: string) => void;
}

/** Status dot: same certainty scale as the map; reviewed gets a ring, "nicht bestimmbar" is hollow. */
const DOT: Record<ReturnType<typeof certClass>, string> = {
  confirmed: "bg-cert-confirmed ring-1 ring-cert-confirmed ring-offset-1 ring-offset-paper",
  sure: "bg-cert-sure",
  check: "bg-cert-check",
  open: "border border-cert-open bg-paper",
};

export default function PhotoRow({ item, hovered, selected, onHover, onSelect }: Props) {
  const { record, result } = item;
  const series = record.raw?.session?.length ?? 0;
  const l = lines(item);
  return (
    <li id={rowId(record.id)}>
      <Link
        href={analyseHref(record.id)}
        aria-current={selected ? "true" : undefined}
        title={selected ? "Erneut klicken oder Enter öffnet das Foto" : undefined}
        onMouseEnter={() => onHover?.(record.id)}
        onMouseLeave={() => onHover?.(null)}
        onFocus={() => onHover?.(record.id)}
        onBlur={() => onHover?.(null)}
        onClick={(e) => {
          if (onSelect && !selected) {
            e.preventDefault();
            onSelect(record.id);
          }
        }}
        className={cn(
          "group relative flex gap-3 rounded p-2 transition-colors duration-hover hover:bg-paper-2/70",
          FOCUS_RING,
          hovered && !selected && "bg-paper-2/70",
          selected && "bg-accent-soft/[0.07] ring-1 ring-inset ring-accent/25",
        )}
      >
        <span className="relative shrink-0 overflow-hidden rounded-sm bg-paper-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageUrl(record.id, 320)}
            alt=""
            loading="lazy"
            className="h-[84px] w-[112px] object-cover transition-transform duration-500 ease-calm group-hover:scale-[1.04]"
          />
          {series > 0 && (
            <span className="absolute bottom-1 left-1 rounded-sm bg-black/55 px-1 text-micro text-white backdrop-blur-sm">
              Serie {series + 1}
            </span>
          )}
        </span>
        <span className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
          <span className="flex items-center gap-2 text-meta tnum">
            <span className={cn("size-1.5 shrink-0 rounded-dot", DOT[certClass(result)])} aria-hidden />
            <span className="truncate font-mono text-ink-muted">{record.signature ?? record.id}</span>
            {result && (
              <span className={cn("ml-auto shrink-0 font-medium", l.warn ? "text-warn" : "text-ink")}>
                {formatPct(result.overall_confidence)}
              </span>
            )}
          </span>
          <span className="truncate text-ui font-medium text-ink">{l.headline}</span>
          {l.sub && <span className="truncate text-meta text-ink-muted">{l.sub}</span>}
          {/* "sicher" says nothing the dot and the percentage do not; the other states do. */}
          {l.status && l.status !== "sicher" && (
            <span className={cn("text-micro", l.warn ? "text-warn" : "text-ink-muted")}>{l.status}</span>
          )}
        </span>
      </Link>
    </li>
  );
}
