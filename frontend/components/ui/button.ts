// Button recipes (FRONTPAGE_POLISH 4): 32px, soft. Primary red only for the commit actions
// (Bestätigen, Speichern, Excel herunterladen); secondary is a soft fill; ghost is text only.
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost";

export const FOCUS_RING =
  "outline-none focus-visible:ring-2 focus-visible:ring-focus/50 focus-visible:ring-offset-1 focus-visible:ring-offset-paper";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "px-3 bg-accent text-white hover:bg-accent-hover active:translate-y-px",
  secondary: "px-3 bg-paper-2 text-ink hover:bg-rule/[0.08]",
  ghost: "px-2 text-ink-muted hover:bg-paper-2 hover:text-ink",
};

/** Class string for a <button> or an <a> that looks like one. */
export function buttonClass(variant: ButtonVariant = "secondary", className?: string): string {
  return cn(
    "inline-flex h-8 items-center justify-center gap-1.5 rounded text-ui font-medium transition-colors duration-hover disabled:pointer-events-none disabled:opacity-50",
    FOCUS_RING,
    VARIANTS[variant],
    className,
  );
}
