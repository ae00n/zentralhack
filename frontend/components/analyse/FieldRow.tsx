"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { formatAny } from "@/lib/format";
import { evidenceLabel } from "@/lib/labels";
import type { AnalysisResult, Evidence } from "@/lib/types";
import Confidence, { REVIEW_THRESHOLD } from "./Confidence";

type Rejected = AnalysisResult["rejected_hypotheses"][number];

interface Props {
  label: string;
  value: string;
  confidence: number;
  evidence: Evidence[];
  rejected: Rejected[];
}

export default function FieldRow({ label, value, confidence, evidence, rejected }: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const low = confidence < REVIEW_THRESHOLD;
  const expandable = evidence.length > 0 || rejected.length > 0;

  return (
    <div className="py-2.5">
      <button
        type="button"
        onClick={() => expandable && setOpen((o) => !o)}
        aria-expanded={expandable ? open : undefined}
        aria-controls={expandable ? panelId : undefined}
        className={`grid w-full grid-cols-[88px_1fr_auto_16px] items-baseline gap-3 text-left ${expandable ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="text-meta text-ink-muted">{label}</span>
        <span className="min-w-0">
          <span className="break-words">{value}</span>
          {low && <span className="ml-2 text-meta text-warn">Prüfung nötig</span>}
        </span>
        <Confidence value={confidence} />
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

      {rejected.length > 0 && !open && (
        <p className="ml-[100px] mt-0.5 text-meta text-ink-muted">
          Verworfen: {rejected.map((r) => formatAny(r.value)).join(", ")}
        </p>
      )}

      {open && (
        <div id={panelId} className="fade-in ml-[100px] mt-2 space-y-2">
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
                <li key={i} className="text-meta">
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

function EvidenceItem({ evidence: e }: { evidence: Evidence }) {
  return (
    <li className="grid grid-cols-[56px_1fr] gap-2 text-meta">
      <span className={e.supports ? "text-ink-muted" : "text-warn"}>{e.supports ? "dafür" : "dagegen"}</span>
      <span>
        {e.summary}
        <span className="text-ink-muted">
          {" · "}
          {evidenceLabel(e.kind)}
          {typeof e.score === "number" && <span className="font-mono"> · {e.score.toFixed(2)}</span>}
        </span>
        {e.url && (
          <>
            {" · "}
            <a href={e.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
              Quelle
            </a>
          </>
        )}
      </span>
    </li>
  );
}
