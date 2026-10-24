// Head of the desk list panel (FRONTPAGE_POLISH 5): title, meta, the three model counters as a compact
// KPI strip (still the filters), and the Prio-1 review progress. Phone: counters as one meta line and the
// full-width Excel button (the header hides it there).
import { Download } from "lucide-react";
import { FOCUS_RING, buttonClass } from "@/components/ui/button";
import { cn } from "@/lib/cn";
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

function Kpi({ value, label, note, active, onClick }: { value: number; label: string; note: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={note}
      className={cn(
        "rounded px-2 py-1.5 text-left transition-colors duration-hover hover:bg-paper-2",
        FOCUS_RING,
        active && "bg-paper-2",
      )}
    >
      <span className="block text-kpi tnum text-ink">{value}</span>
      <span className="block text-meta text-ink-muted">{label}</span>
    </button>
  );
}

export default function DeskBand({ meta, counts, prio, filter, onFilter, excelUrl }: Props) {
  const toggle = (f: FilterKey) => onFilter(filter === f ? "all" : f);
  const share = prio.total ? prio.reviewed / prio.total : 0;
  return (
    <section className="border-b border-rule/[0.08] p-3">
      <h1 className="text-h3 text-ink">Erschliessung SG.CIV.17</h1>
      <p className="mt-0.5 text-meta tnum text-ink-muted">{meta}</p>

      {/* Phone: the counters collapse into one meta line (plan 4). */}
      <p className="mt-2 text-meta tnum sm:hidden">
        {counts.sure} sicher · <span className="text-warn">{counts.check} Prüfung nötig</span> · {counts.open} nicht
        bestimmbar
      </p>
      <div className="-mx-2 mt-2 hidden grid-cols-3 gap-1 sm:grid">
        <Kpi value={counts.sure} label="sicher" note="ab 90 %" active={filter === "sure"} onClick={() => toggle("sure")} />
        <Kpi value={counts.check} label="Prüfung nötig" note="unter 90 %" active={filter === "check"} onClick={() => toggle("check")} />
        <Kpi
          value={counts.open}
          label="nicht bestimmbar"
          note={counts.withoutResult ? `Ort offen · ${counts.withoutResult} ohne Ergebnis` : "Ort offen"}
          active={filter === "open"}
          onClick={() => toggle("open")}
        />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <span className="relative h-1 flex-1 overflow-hidden rounded-sm bg-paper-2" aria-hidden>
          <span className="absolute inset-y-0 left-0 bg-ink transition-[width] duration-500 ease-calm" style={{ width: `${share * 100}%` }} />
        </span>
        <span className="text-meta tnum text-ink">
          {prio.reviewed} / {prio.total}
        </span>
      </div>
      <p className="mt-1 text-meta tnum text-ink-muted">
        Prio 1 geprüft · {formatPct(share)} · {prio.confirmed} bestätigt · {prio.corrected} korrigiert
      </p>

      <a href={excelUrl} download className={buttonClass("primary", "mt-3 h-10 w-full sm:hidden")}>
        <Download size={16} strokeWidth={1.75} aria-hidden />
        Excel herunterladen
      </a>
    </section>
  );
}
