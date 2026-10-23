"use client";

// One field of the Erschliessung (FRONTPAGE_POLISH 4 field row recipe): label | value | Modell-Sicherheit
// on one grid, the meta line (top source kinds + provenance) under the value, the evidence list on expand.
// In edit mode the value column holds an input, the same width in every row.
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { FOCUS_RING } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { analyseHref, formatAny } from "@/lib/format";
import { evidenceLabel } from "@/lib/labels";
import type { AnalysisResult, Evidence } from "@/lib/types";
import Confidence from "./Confidence";

type Rejected = AnalysisResult["rejected_hypotheses"][number];

interface Props {
  label: string;
  /** Display value; "nicht bestimmbar" when empty. */
  value: string;
  empty: boolean;
  /** Set when the archivist corrected the field: the AI value, shown struck through. */
  aiValue?: string;
  confidence: number;
  evidence: Evidence[];
  rejected: Rejected[];
  /** "KI-Vorschlag · ungeprüft", "korrigiert · KI: Brunnen", ... */
  provenance: string;
  /** Korrigieren: an input that replaces the value in place. */
  editor?: ReactNode;
  /** Review field key, so the page can focus this row (weakest field, keys 1 to 5). */
  fieldKey?: string;
}

const GRID = "grid grid-cols-[88px_minmax(0,1fr)_56px] items-baseline gap-x-3 sm:grid-cols-[112px_minmax(0,1fr)_56px]";

/** Top supporting source kinds, German, without repeats: "Adressverzeichnis · Benanntes Gebäude". */
function sourceKinds(evidence: Evidence[], max = 3): string[] {
  return [...new Set(evidence.filter((e) => e.supports !== false).map((e) => evidenceLabel(e.kind)))].slice(0, max);
}

export default function FieldRow({
  label,
  value,
  empty,
  aiValue,
  confidence,
  evidence,
  rejected,
  provenance,
  editor,
  fieldKey,
}: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const expandable = evidence.length > 0 || rejected.length > 0;
  const meta = [...sourceKinds(evidence), provenance].join(" · ");
  // "nicht bestimmbar" rows show no percentage (FRONTPAGE_PLAN 5).
  const percent = empty && aiValue === undefined ? <span /> : <Confidence value={confidence} />;

  if (editor) {
    return (
      <label className={cn(GRID, "border-b border-rule/[0.06] py-2.5")}>
        <span className="text-meta text-ink-muted">{label}</span>
        <span className="min-w-0">
          {editor}
          <span className="mt-1 block truncate text-meta text-ink-muted">KI: {aiValue ?? value}</span>
        </span>
        <span className="text-right">{percent}</span>
      </label>
    );
  }

  return (
    <div className="border-b border-rule/[0.06]">
      <button
        type="button"
        data-review-field={fieldKey}
        onClick={() => expandable && setOpen((o) => !o)}
        aria-expanded={expandable ? open : undefined}
        aria-controls={expandable ? panelId : undefined}
        className={cn(
          GRID,
          "w-full rounded-sm py-3 text-left transition-colors duration-hover",
          FOCUS_RING,
          expandable ? "cursor-pointer hover:bg-paper-2/50" : "cursor-default",
        )}
      >
        <span className="flex items-center gap-1 text-meta text-ink-muted">
          {label}
          {expandable && (
            <ChevronRight
              size={12}
              strokeWidth={1.75}
              aria-hidden
              className={cn("shrink-0 transition-transform duration-hover", open && "rotate-90")}
            />
          )}
        </span>
        <span className="min-w-0">
          <span className="block">
            {aiValue !== undefined && (
              <>
                <s className="text-base text-ink-muted">{aiValue}</s>
                <span className="text-ink-muted"> → </span>
              </>
            )}
            <span className={cn("break-words text-base", empty ? "text-ink-muted" : "font-medium text-ink")}>{value}</span>
          </span>
          <span className="mt-0.5 block text-meta text-ink-muted">{meta}</span>
          {rejected.length > 0 && !open && (
            <span className="block text-meta text-ink-muted">Verworfen: {rejected.map((r) => formatAny(r.value)).join(", ")}</span>
          )}
        </span>
        <span className="text-right">{percent}</span>
      </button>

      {open && (
        <div id={panelId} className={cn(GRID, "pb-3 animate-in fade-in duration-300")}>
          <span />
          <div className="col-span-2 space-y-2">
            {evidence.length > 0 && (
              <ul className="space-y-1.5">
                {evidence.map((e, i) => (
                  <EvidenceItem key={i} evidence={e} />
                ))}
              </ul>
            )}
            {rejected.length > 0 && (
              <ul className="space-y-1.5 border-t border-rule/[0.06] pt-2">
                {rejected.map((r, i) => (
                  <li key={i} className="text-ui">
                    <span className="text-ink-muted">Verworfen: </span>
                    <span className="font-medium">{formatAny(r.value)}</span>
                    <span className="text-ink-muted">. {r.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Staatsarchiv catalogue page for a stasz: record id. */
function catalogueUrl(refId: string): string | null {
  const m = /^stasz:(\d+)/.exec(refId);
  return m ? `https://query.staatsarchiv.sz.ch/detail.aspx?ID=${m[1]}` : null;
}

function EvidenceItem({ evidence: e }: { evidence: Evidence }) {
  const catalogue = e.ref_id ? catalogueUrl(e.ref_id) : null;
  return (
    <li className="text-ui">
      {e.supports === false && <span className="text-warn">spricht dagegen: </span>}
      {e.summary}
      <span className="text-ink-muted">
        {" · "}
        {evidenceLabel(e.kind)}
        {typeof e.score === "number" && <span className="tnum"> · {e.score.toFixed(2)}</span>}
      </span>
      {e.url && (
        <>
          {" · "}
          <a href={e.url} target="_blank" rel="noreferrer" className="link">
            Quelle
          </a>
        </>
      )}
      {catalogue && (
        <>
          {" · "}
          <a href={catalogue} target="_blank" rel="noreferrer" className="link">
            im Katalog
          </a>
        </>
      )}
      {e.ref_id && !catalogue && (
        <>
          {" · "}
          <Link href={analyseHref(e.ref_id)} className="link">
            Referenzfoto ansehen
          </Link>
        </>
      )}
    </li>
  );
}
