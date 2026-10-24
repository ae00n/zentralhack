import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import ResultPanel from "@/components/analyse/ResultPanel";
import { FOCUS_RING } from "@/components/ui/button";
import { imageUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { certClass, type DeskItem } from "@/lib/desk";
import { candidateNote, candidatesOf, photoMarksOf, type Candidate } from "@/lib/reasoning";
import { SURE } from "@/lib/review";
import { analyseHref, formatPct } from "@/lib/format";

// The picked photo in the desk's side panel (Said, 24.10.): picking a photo on the map or in the list
// shows its result here instead of the list; "Zurück" (or Escape) brings the list back. The full page
// with trace and review stays one click away.

const STATUS: Record<ReturnType<typeof certClass>, { label: string; cls: string }> = {
  confirmed: { label: "bestätigt", cls: "bg-cert-confirmed/15 text-cert-confirmed" },
  sure: { label: "sicher", cls: "bg-cert-sure/15 text-cert-sure" },
  check: { label: "Prüfung nötig", cls: "bg-cert-check/15 text-cert-check" },
  open: { label: "nicht bestimmbar", cls: "bg-paper-2 text-ink-muted" },
};

/** The places the agent weighed, A first; the same letters as on the map. */
function Candidates({ list, unsure }: { list: Candidate[]; unsure: boolean }) {
  return (
    <section className="px-3 pt-3">
      <h2 className="text-micro font-medium uppercase tracking-[0.08em] text-ink-muted">
        {unsure ? "Mögliche Orte" : "Geprüft und verworfen"}
      </h2>
      <ol className="mt-1.5 space-y-1">
        {list.map((c) => (
          <li key={c.letter} className="flex items-start gap-2.5 rounded bg-paper-2/60 px-2 py-1.5">
            <span
              aria-hidden
              className={cn(
                "mt-0.5 grid size-5 shrink-0 place-items-center rounded-dot text-micro font-bold",
                c.chosen ? "bg-accent text-white" : unsure ? "bg-paper text-ink ring-1 ring-ink/70" : "bg-ink-muted text-white",
              )}
            >
              {c.letter}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-2">
                <span className={cn("truncate text-ui", c.chosen ? "font-medium text-ink" : "text-ink")}>{c.name}</span>
                <span className="ml-auto shrink-0 text-micro tnum text-ink-muted">
                  {c.chosen ? (unsure ? "wahrscheinlichster" : "gewählt") : `${c.km < 1 ? `${Math.round(c.km * 1000)} m` : `${c.km.toFixed(1)} km`}`}
                </span>
              </span>
              <span className="block truncate text-micro text-ink-muted">
                {[c.where, candidateNote(c)].filter(Boolean).join(" · ")}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

interface Props {
  item: DeskItem;
  onBack: () => void;
}

export default function PhotoDetail({ item, onBack }: Props) {
  const { record, result } = item;
  const status = STATUS[certClass(result)];
  const series = record.raw?.session?.length ?? 0;
  const candidates = candidatesOf(result);
  return (
    <div className="detail-enter flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-rule/[0.08] px-2 py-2">
        <button
          type="button"
          onClick={onBack}
          className={cn(
            "inline-flex items-center gap-1.5 rounded px-2 py-1 text-ui text-ink transition-colors duration-hover hover:bg-paper-2",
            FOCUS_RING,
          )}
        >
          <ArrowLeft className="size-4" aria-hidden />
          Zurück
        </button>
        <span className="ml-auto truncate font-mono text-ui text-ink-muted">{record.signature ?? record.id}</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="relative">
          <div className="burn-in">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageUrl(record.id, 960)} alt={`Foto ${record.signature ?? record.id}`} className="block w-full bg-paper-2" />
          </div>
          {/* The same landmarks as on the map, with the same icons (Said, 24.10.): placed where they are in the
              photo, or as a pointer on the top edge when only their direction is known. */}
          {photoMarksOf(result).map((m, i) => (
            <span
              key={m.name}
              className={cn("photo-mark", m.kind, m.y === null ? "edge" : m.x > 0.6 && "flip")}
              style={{ left: `${m.x * 100}%`, top: m.y === null ? 0 : `${m.y * 100}%`, animationDelay: `${1150 + i * 220}ms` }}
            >
              <i aria-hidden />
              <span>{m.name}</span>
            </span>
          ))}
        </div>

        <div className="write-in">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 pt-3">
          <span className={cn("rounded-sm px-2 py-0.5 text-meta font-medium", status.cls)}>{status.label}</span>
          {result && <span className="text-meta tnum text-ink-muted">Gesamt {formatPct(result.overall_confidence)}</span>}
          {record.date?.raw && <span className="text-meta tnum text-ink-muted">Aufnahme {record.date.raw}</span>}
          {series > 0 && <span className="text-meta text-ink-muted">Serie ({series + 1})</span>}
        </div>

        {candidates.length > 0 && <Candidates list={candidates} unsure={(result?.overall_confidence ?? 0) < SURE} />}

        <div className="px-3 pb-3 pt-2">
          {result ? (
            <ResultPanel result={result} />
          ) : (
            <p className="py-6 text-ui text-ink-muted">Noch kein Ergebnis für dieses Foto.</p>
          )}
        </div>
        </div>
      </div>

      <div className="border-t border-rule/[0.08] p-2">
        <Link
          href={analyseHref(record.id)}
          className={cn(
            "flex items-center justify-center gap-1.5 rounded bg-ink px-3 py-2 text-ui font-medium text-paper transition-opacity duration-hover hover:opacity-90",
            FOCUS_RING,
          )}
        >
          Vollansicht, Herleitung und Prüfung
          <ArrowUpRight className="size-4" aria-hidden />
        </Link>
      </div>
    </div>
  );
}
