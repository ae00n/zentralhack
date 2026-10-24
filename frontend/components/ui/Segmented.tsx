"use client";

// Segmented control (FRONTPAGE_POLISH 4): soft track, the active item lifts to white. 4px radius, no pills.
import { cn } from "@/lib/cn";
import { FOCUS_RING } from "./button";

interface Props<K extends string> {
  value: K;
  options: { key: K; label: string }[];
  onChange: (key: K) => void;
  label: string;
  /** "tab" for view switches (Liste | Karte), "button" for filters (Prio 1 | Alle). */
  role?: "tab" | "button";
  className?: string;
}

export default function Segmented<K extends string>({ value, options, onChange, label, role = "button", className }: Props<K>) {
  return (
    <div
      role={role === "tab" ? "tablist" : "group"}
      aria-label={label}
      className={cn("inline-grid grid-flow-col gap-0.5 rounded bg-paper-2 p-0.5", className)}
    >
      {options.map((o) => {
        const active = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role={role === "tab" ? "tab" : undefined}
            aria-selected={role === "tab" ? active : undefined}
            aria-pressed={role === "button" ? active : undefined}
            onClick={() => onChange(o.key)}
            className={cn(
              "h-7 rounded-sm px-2.5 text-ui transition-colors duration-hover",
              FOCUS_RING,
              active ? "bg-paper font-medium text-ink shadow-[0_1px_2px_rgb(0_0_0/0.06)]" : "text-ink-muted hover:text-ink",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
