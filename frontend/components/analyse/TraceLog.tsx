"use client";

// Quiet log of the agent's steps. Lines fade in as they arrive; collapsible once the analysis is done.
import { toolLabel } from "@/lib/labels";
import type { TraceItem } from "@/lib/types";

interface Props {
  items: TraceItem[];
  running: boolean;
  /** Collapsed on the phone once the analysis is done. */
  defaultOpen?: boolean;
}

export default function TraceLog({ items, running, defaultOpen = true }: Props) {
  const list = (
    <ol className="mt-2 space-y-1.5">
      {items.map((item) => (
        <li key={item.step} className="fade-in grid grid-cols-[24px_1fr] gap-2 text-ui">
          <span className="font-mono text-ink-muted">{item.step}</span>
          <TraceLine item={item} />
        </li>
      ))}
      {running && <li className="pl-8 text-ui text-ink-muted">...</li>}
    </ol>
  );

  return (
    <details open={running || defaultOpen}>
      <summary className="cursor-pointer text-h3 hover:text-ink-strong">
        So entsteht das Ergebnis{running ? " ..." : ` · ${items.length} Schritte`}
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
