"use client";

// Radix Select styled like the search field (FRONTPAGE_POLISH 4). Needs "use client": radix-ui crashes in RSC.
import { Check, ChevronDown } from "lucide-react";
import { Select as S } from "radix-ui";
import { cn } from "@/lib/cn";
import { FOCUS_RING } from "./button";

interface Props<K extends string> {
  value: K;
  options: { key: K; label: string }[];
  onChange: (key: K) => void;
  /** Accessible name; also shown before the value when `prefix` is set. */
  label: string;
  prefix?: boolean;
  className?: string;
}

export default function Select<K extends string>({ value, options, onChange, label, prefix, className }: Props<K>) {
  return (
    <S.Root value={value} onValueChange={(v) => onChange(v as K)}>
      <S.Trigger
        aria-label={label}
        className={cn(
          "inline-flex h-8 items-center gap-1.5 rounded border border-rule/[0.12] bg-paper px-2.5 text-ui text-ink transition-colors duration-hover hover:border-rule/20",
          FOCUS_RING,
          className,
        )}
      >
        {prefix && <span className="text-ink-muted">{label}:</span>}
        <S.Value />
        <S.Icon className="ml-auto text-ink-muted">
          <ChevronDown size={14} strokeWidth={1.75} />
        </S.Icon>
      </S.Trigger>
      <S.Portal>
        <S.Content
          position="popper"
          sideOffset={4}
          className="z-50 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-rule/[0.08] bg-paper p-1 shadow-panel animate-in fade-in duration-200"
        >
          <S.Viewport>
            {options.map((o) => (
              <S.Item
                key={o.key}
                value={o.key}
                className="relative flex h-8 cursor-default select-none items-center rounded-sm pl-2 pr-7 text-ui text-ink outline-none data-[highlighted]:bg-paper-2"
              >
                <S.ItemText>{o.label}</S.ItemText>
                <S.ItemIndicator className="absolute right-2 text-ink-muted">
                  <Check size={14} strokeWidth={1.75} />
                </S.ItemIndicator>
              </S.Item>
            ))}
          </S.Viewport>
        </S.Content>
      </S.Portal>
    </S.Root>
  );
}
