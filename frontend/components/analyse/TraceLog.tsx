"use client";

// Quiet log of the agent's steps. Lines fade in as they arrive; collapsible once the analysis is done.
// Short for the pitch (Said, 24.10.): one line per step, the full text behind "mehr", the image check as
// bars, no timings. Also used by the live view after an upload.
import { useState } from "react";
import AerialCompare, { type AerialCandidate } from "@/components/analyse/AerialCompare";
import { cn } from "@/lib/cn";
import { stepView } from "@/lib/trace";
import type { TraceItem } from "@/lib/types";

interface Props {
  items: TraceItem[];
  running: boolean;
  /** Collapsed on the phone once the analysis is done. */
  defaultOpen?: boolean;
  /** Tile base and capture year: "aerial_view" steps show the aerial photos the agent compared. */
  aerial?: { tilesUrl: string; year?: number };
}

export default function TraceLog({ items, running, defaultOpen = true, aerial }: Props) {
  const list = (
    <ol className="mt-2 space-y-2.5">
      {items.map((item, i) => (
        <li key={item.step} className="fade-in grid grid-cols-[20px_1fr] gap-2.5">
          <span
            aria-hidden
            className={cn(
              "mt-px grid size-5 place-items-center rounded-dot text-micro tnum",
              item.type === "final" ? "bg-ink text-paper" : "bg-paper-2 text-ink-muted",
            )}
          >
            {i + 1}
          </span>
          <span className="min-w-0">
            <TraceLine item={item} />
            {aerial && item.type === "tool_call" && item.tool === "aerial_view" && (
              <AerialCompare
                candidates={((item.input?.candidates as AerialCandidate[] | undefined) ?? [])}
                radiusM={Number(item.input?.radius_m) || 70}
                tilesUrl={aerial.tilesUrl}
                year={aerial.year}
              />
            )}
          </span>
        </li>
      ))}
      {running && <li className="pl-[30px] text-ui text-ink-muted">...</li>}
    </ol>
  );

  return (
    <details open={running || defaultOpen}>
      <summary className="cursor-pointer list-none text-meta font-medium uppercase tracking-[0.06em] text-ink-muted hover:text-ink">
        So entsteht das Ergebnis
        <span className="ml-1.5 normal-case tracking-normal">{running ? "..." : `${items.length} Schritte ▸`}</span>
      </summary>
      {list}
    </details>
  );
}

function TraceLine({ item }: { item: TraceItem }) {
  const v = stepView(item);
  const [open, setOpen] = useState(false);
  return (
    <span className="block">
      <span className="block text-meta text-ink-muted">{v.label}</span>
      {v.short && <span className={cn("block text-ui text-ink", v.final && "font-medium")}>{v.short}</span>}
      {v.bars && <Bars bars={v.bars} />}
      {v.detail && (
        <>
          {open && <span className="mt-1 block text-meta text-ink-muted">{v.detail}</span>}
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="mt-0.5 text-micro text-ink-muted underline decoration-rule/20 underline-offset-2 hover:text-ink"
          >
            {open ? "weniger" : "mehr"}
          </button>
        </>
      )}
    </span>
  );
}

/** Image check points per place: the best one dark, the rest grey, scaled to the best. */
function Bars({ bars }: { bars: { name: string; points: number }[] }) {
  const max = Math.max(...bars.map((b) => b.points), 1);
  return (
    <span className="mt-1 block space-y-1">
      {bars.slice(0, 5).map((b, i) => (
        <span key={b.name} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-2 text-meta">
          <span className={cn("truncate", i === 0 ? "text-ink" : "text-ink-muted")}>{b.name}</span>
          <span className="h-1.5 overflow-hidden rounded-sm bg-paper-2">
            <span
              className={cn("block h-full rounded-sm", i === 0 ? "bg-ink" : "bg-ink-muted/40")}
              style={{ width: `${(b.points / max) * 100}%` }}
            />
          </span>
          <span className={cn("tnum", i === 0 ? "font-medium text-ink" : "text-ink-muted")}>{b.points}</span>
        </span>
      ))}
    </span>
  );
}
