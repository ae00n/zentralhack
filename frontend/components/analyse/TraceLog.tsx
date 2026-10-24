"use client";

// Quiet log of the agent's steps. Lines fade in as they arrive; collapsible once the analysis is done.
import AerialCompare, { type AerialCandidate } from "@/components/analyse/AerialCompare";
import { toolLabel } from "@/lib/labels";
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
    <ol className="mt-2 space-y-1.5">
      {items.map((item) => (
        <li key={item.step} className="fade-in grid grid-cols-[24px_1fr] gap-2 text-ui">
          <span className="font-mono text-ink-muted">{item.step}</span>
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
      {running && <li className="pl-8 text-ui text-ink-muted">...</li>}
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
  if (item.type === "tool_call") {
    return (
      <span>
        <span className="text-ink-muted">{toolLabel(item.tool)}</span>
        {item.output_summary && <span>: {item.output_summary}</span>}
        {item.ms > 0 && <span className="font-mono text-ink-muted"> · {item.ms} ms</span>}
      </span>
    );
  }
  if (item.type === "final") {
    return <span className="font-medium">{item.text}</span>;
  }
  return <span className="text-ink-muted">{item.text ?? item.output_summary ?? item.type}</span>;
}
