// cn(): join class names and let later Tailwind classes win (clsx + tailwind-merge).
// tailwind-merge 2.x, because 3.x only supports Tailwind v4. The custom font sizes are registered so
// "text-ui" and "text-ink" are not treated as the same group.
import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["micro", "meta", "ui", "base", "h3", "h2", "h1", "kpi", "hero"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
