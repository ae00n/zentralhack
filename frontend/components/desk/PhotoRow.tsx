import Link from "next/link";
import { FOCUS_RING } from "@/components/ui/button";
import { imageUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { certClass, modelClass, type DeskItem } from "@/lib/desk";
import { NOT_DETERMINED, analyseHref, formatPct, isEmptyValue } from "@/lib/format";
import { effectiveValue, formatValue } from "@/lib/review";

// Flat list row (sz.ch list, FRONTPAGE_PLAN 2.2): thumbnail, bold signature line, one meta line,
// 1px divider. Meta: "Schwyz · Alterszentrum Acherhof · Grundstrasse 32 · 94 % · bestätigt".
// Plan 4 behaviour: hover highlights the pin, the first click selects (map flies there), a second
// click or Enter opens the detail page.

function metaParts(item: DeskItem): { text: string; warn?: boolean }[] {
  const { result } = item;
  if (!result) return [{ text: "Noch kein Ergebnis" }];
  const first = (v: ReturnType<typeof effectiveValue>) => (Array.isArray(v) ? v[0] : v);
  const place = effectiveValue(result, "locality") ?? effectiveValue(result, "municipality");
  const building = first(effectiveValue(result, "buildings"));
  const street = effectiveValue(result, "street");
  const parts: { text: string; warn?: boolean }[] = [
    { text: formatValue(place) },
    { text: building ?? NOT_DETERMINED },
  ];
  if (!isEmptyValue(street)) parts.push({ text: formatValue(street) });
  parts.push({ text: formatPct(result.overall_confidence) });
  const status = result.review?.status;
  if (status === "bestaetigt") parts.push({ text: "bestätigt" });
  else if (status === "korrigiert") parts.push({ text: "korrigiert" });
  else if (modelClass(result) === "sure") parts.push({ text: "sicher" });
  else parts.push({ text: "Prüfung nötig", warn: true });
  return parts;
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

/** Status dot (6 px): same certainty scale as the map; reviewed gets a ring, "nicht bestimmbar" is hollow. */
const DOT: Record<ReturnType<typeof certClass>, string> = {
  confirmed: "bg-cert-confirmed ring-1 ring-cert-confirmed ring-offset-1 ring-offset-paper",
  sure: "bg-cert-sure",
  check: "bg-cert-check",
  open: "border border-cert-open",
};

export default function PhotoRow({ item, hovered, selected, onHover, onSelect }: Props) {
  const { record } = item;
  const series = record.raw?.session?.length ?? 0;
  return (
    <li id={rowId(record.id)}>
      <Link
        href={analyseHref(record.id)}
        aria-current={selected ? "true" : undefined}
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
          "group relative grid grid-cols-[64px_minmax(0,1fr)] gap-3 border-b border-rule/[0.06] px-3 py-2.5 transition-colors duration-hover hover:bg-paper-2/70",
          FOCUS_RING,
          "focus-visible:ring-inset focus-visible:ring-offset-0",
          hovered && !selected && "bg-paper-2/70",
          selected && "bg-accent-soft/[0.06] before:absolute before:inset-y-2 before:left-0 before:w-[2px] before:bg-accent",
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl(record.id, 160)} alt="" loading="lazy" className="h-11 w-16 rounded-sm bg-paper-2 object-cover" />
        <span className="min-w-0">
          <span className="flex items-center gap-2">
            <span className={cn("size-1.5 shrink-0 rounded-dot", DOT[certClass(item.result)])} aria-hidden />
            <span className="font-mono text-ui text-ink">{record.signature ?? record.id}</span>
            {series > 0 && <span className="text-meta text-ink-muted">Serie ({series + 1})</span>}
          </span>
          <span className="mt-0.5 block truncate text-meta tnum text-ink-muted">
            {metaParts(item).map((p, i) => (
              <span key={i}>
                {i > 0 && " · "}
                <span className={p.warn ? "text-warn" : undefined}>{p.text}</span>
              </span>
            ))}
          </span>
          {selected && <span className="mt-0.5 block text-micro text-ink-muted">Erneut klicken oder Enter öffnet das Foto</span>}
        </span>
      </Link>
    </li>
  );
}
