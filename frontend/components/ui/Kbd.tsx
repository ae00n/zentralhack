import { cn } from "@/lib/cn";

// Key hint (FRONTPAGE_POLISH 4): small, soft, hidden on touch screens. `onAccent` for red buttons.
export default function Kbd({ children, onAccent, className }: { children: React.ReactNode; onAccent?: boolean; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-sm border px-1 font-mono text-micro shadow-kbd [@media(pointer:coarse)]:hidden",
        onAccent ? "border-white/20 bg-white/20 text-white" : "border-rule/[0.10] bg-paper-2 text-ink-muted",
        className,
      )}
    >
      {children}
    </kbd>
  );
}
