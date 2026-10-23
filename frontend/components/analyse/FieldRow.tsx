"use client";

// One field of the Erschliessung (FRONTPAGE_PLAN 5, "Field rows"): label | value | Modell-Sicherheit,
// a meta line with the top source kinds and the provenance, and the evidence list on expand.
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
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

  if (editor) {
    return (
      <div className="py-3">
        <label className="grid w-full grid-cols-[112px_1fr_auto_16px] items-baseline gap-3">
          <span className="text-small text-ink-muted">{label}</span>
          {editor}
          {empty ? <span /> : <Confidence value={confidence} />}
          <span />
        </label>
        <p className="ml-[124px] mt-0.5 text-meta text-ink-muted">KI: {aiValue ?? value}</p>
      </div>
    );
  }

  return (
    <div className="py-3">
      <button
        data-review-field={fieldKey}
        type="button"
        onClick={() => expandable && setOpen((o) => !o)}
        aria-expanded={expandable ? open : undefined}
        aria-controls={expandable ? panelId : undefined}
        className={`grid w-full grid-cols-[112px_1fr_auto_16px] items-baseline gap-3 text-left ${expandable ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="text-small text-ink-muted">{label}</span>
        <span className="min-w-0">
          {aiValue !== undefined && (
            <>
              <s className="text-ink-muted">{aiValue}</s>
              <span className="text-ink-muted"> → </span>
            </>
          )}
          <span className={`break-words text-body ${empty ? "text-ink-muted" : "font-medium"}`}>{value}</span>
        </span>
        {/* "nicht bestimmbar" rows show no percentage (plan 5). */}
        {empty && aiValue === undefined ? <span /> : <Confidence value={confidence} />}
        {expandable ? (
          <ChevronDown
            size={16}
            strokeWidth={1.5}
            className={`self-center text-ink-muted transition-transform duration-300 ${open ? "rotate-180" : ""}`}
          />
        ) : (
          <span />
        )}
      </button>

      <p className="ml-[124px] mt-0.5 text-meta text-ink-muted">{meta}</p>
      {rejected.length > 0 && !open && (
        <p className="ml-[124px] text-meta text-ink-muted">Verworfen: {rejected.map((r) => formatAny(r.value)).join(", ")}</p>
      )}

      {open && (
        <div id={panelId} className="fade-in ml-[124px] mt-2 space-y-2">
          {evidence.length > 0 && (
            <ul className="space-y-1.5">
              {evidence.map((e, i) => (
                <EvidenceItem key={i} evidence={e} />
              ))}
            </ul>
          )}
          {rejected.length > 0 && (
            <ul className="space-y-1.5 border-t border-rule pt-2">
              {rejected.map((r, i) => (
                <li key={i} className="text-small">
                  <span className="text-ink-muted">Verworfen: </span>
                  <span className="font-medium">{formatAny(r.value)}</span>
                  <span className="text-ink-muted">. {r.reason}</span>
                </li>
              ))}
            </ul>
          )}
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
    <li className="text-small">
      {e.supports === false && <span className="text-warn">spricht dagegen: </span>}
      {e.summary}
      <span className="text-ink-muted">
        {" · "}
        {evidenceLabel(e.kind)}
        {typeof e.score === "number" && <span className="font-mono"> · {e.score.toFixed(2)}</span>}
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
