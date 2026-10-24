// Head of the desk list panel. Sidebar makeover (Said, 24.10.): no filters any more, just the title, the
// review progress, and the certainty split as one thin stacked bar with its numbers underneath. Phone: the
// full-width Excel button (the header hides it there).
import { Download } from "lucide-react";
import { buttonClass } from "@/components/ui/button";
import type { Counts } from "@/lib/desk";

interface Props {
  meta: string;
  counts: Counts;
  /** Review progress over the Prio-1 set, whatever the list shows. */
  prio: Counts;
  excelUrl: string;
}

const PARTS = [
  { key: "sure", label: "sicher", bar: "bg-cert-sure" },
  { key: "check", label: "Prüfung nötig", bar: "bg-cert-check" },
  { key: "open", label: "nicht bestimmbar", bar: "bg-cert-open/40" },
] as const;

export default function DeskBand({ meta, counts, prio, excelUrl }: Props) {
  const total = counts.sure + counts.check + counts.open;
  return (
    <section className="px-4 pb-3 pt-4">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-h3 text-ink">Erschliessung SG.CIV.17</h1>
        <span className="shrink-0 text-meta tnum text-ink-muted" title={`${prio.confirmed} bestätigt · ${prio.corrected} korrigiert`}>
          {prio.reviewed} / {prio.total} geprüft
        </span>
      </div>
      <p className="mt-0.5 text-meta tnum text-ink-muted">{meta}</p>

      <div className="mt-3 flex h-1.5 gap-[2px] overflow-hidden rounded-sm bg-paper-2" aria-hidden>
        {PARTS.map((p) =>
          counts[p.key] ? (
            <span
              key={p.key}
              className={`${p.bar} transition-[flex-grow] duration-500 ease-calm`}
              style={{ flexGrow: total ? counts[p.key] / total : 0 }}
            />
          ) : null,
        )}
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-meta tnum text-ink-muted">
        {PARTS.map((p) => (
          <span key={p.key} className="inline-flex items-center gap-1.5">
            <span className={`size-1.5 rounded-dot ${p.bar}`} aria-hidden />
            <span className="font-medium text-ink">{counts[p.key]}</span>
            {p.label}
          </span>
        ))}
      </p>

      <a href={excelUrl} download className={buttonClass("primary", "mt-3 h-10 w-full sm:hidden")}>
        <Download size={16} strokeWidth={1.75} aria-hidden />
        Excel herunterladen
      </a>
    </section>
  );
}
