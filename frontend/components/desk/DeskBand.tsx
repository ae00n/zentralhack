// Context band of the Arbeitsplatz (FRONTPAGE_PLAN 4, sz.ch "Mehr zum Thema" band): title, meta,
// Excel button, and the counters. The three model counters are filters; review progress is Prio 1 only.
import { Download } from "lucide-react";
import type { Counts, FilterKey } from "@/lib/desk";
import { formatPct } from "@/lib/format";

interface Props {
  meta: string;
  counts: Counts;
  /** Review progress over the Prio-1 set, whatever the list shows. */
  prio: Counts;
  filter: FilterKey;
  onFilter: (f: FilterKey) => void;
  excelUrl: string;
}

function Counter({
  value,
  label,
  note,
  active,
  onClick,
}: {
  value: number;
  label: string;
  note: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded border-b-2 px-1 pb-1 text-left transition-colors duration-fade hover:border-ink-muted ${active ? "border-ink-strong" : "border-transparent"}`}
    >
      <span className="block text-counter">{value}</span>
      <span className="block text-body">{label}</span>
      <span className="block text-meta text-ink-muted">{note}</span>
    </button>
  );
}

export default function DeskBand({ meta, counts, prio, filter, onFilter, excelUrl }: Props) {
  const toggle = (f: FilterKey) => onFilter(filter === f ? "all" : f);
  const share = prio.total ? prio.reviewed / prio.total : 0;
  return (
    <section className="bg-paper-2">
      <div className="wrapper py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[30px] font-light leading-9 md:text-page">Erschliessung SG.CIV.17</h1>
            <p className="mt-1 text-small text-ink-muted">{meta}</p>
          </div>
          <a
            href={excelUrl}
            download
            className="inline-flex w-full items-center justify-center gap-2 rounded bg-accent px-4 py-2 font-bold text-white transition-colors duration-fade hover:bg-accent-hover sm:w-auto"
          >
            <Download size={18} strokeWidth={1.5} aria-hidden />
            Excel herunterladen
          </a>
        </div>

        {/* Phone: the counters collapse into one meta line (plan 4). */}
        <p className="mt-4 text-small sm:hidden">
          {counts.sure} sicher · <span className="text-warn">{counts.check} Prüfung nötig</span> · {counts.open} nicht
          bestimmbar
          <span className="block text-ink-muted">
            {prio.reviewed} von {prio.total} Prio 1 geprüft · {prio.corrected} korrigiert
          </span>
        </p>
        <div className="mt-6 hidden flex-wrap items-end gap-x-10 gap-y-4 sm:flex">
          <Counter value={counts.sure} label="sicher" note="ab 90 %" active={filter === "sure"} onClick={() => toggle("sure")} />
          <Counter
            value={counts.check}
            label="Prüfung nötig"
            note="unter 90 %"
            active={filter === "check"}
            onClick={() => toggle("check")}
          />
          <Counter
            value={counts.open}
            label="nicht bestimmbar"
            note={counts.withoutResult ? `Ort offen · ${counts.withoutResult} ohne Ergebnis` : "Ort offen"}
            active={filter === "open"}
            onClick={() => toggle("open")}
          />
          <div className="min-w-[220px] px-1 pb-1">
            <span className="block text-counter">
              {prio.reviewed} <span className="text-body text-ink-muted">von {prio.total}</span>
            </span>
            <span className="block text-body">Prio 1 geprüft</span>
            <span className="mt-1 flex items-center gap-2">
              <span className="relative h-1 w-32 bg-rule" aria-hidden>
                <span className="absolute inset-y-0 left-0 bg-ink" style={{ width: `${share * 100}%` }} />
              </span>
              <span className="font-mono text-meta">{formatPct(share)}</span>
            </span>
            <span className="block text-meta text-ink-muted">
              {prio.confirmed} bestätigt · {prio.corrected} korrigiert
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
