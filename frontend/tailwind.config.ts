import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// "Swiss modern" theme (docs/FRONTPAGE_POLISH.md section 3). Values live as RGB channels in app/globals.css,
// so opacity modifiers work (border-rule/[0.08]). The theme replaces Tailwind's defaults on purpose:
// bg-background, text-sm, shadow-md, neutral-* do nothing here.
const c = (v: string) => `rgb(var(--${v}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#fff",
      black: "#000",
      canvas: c("canvas"),
      paper: c("paper"),
      "paper-2": c("paper-2"),
      rule: c("rule"),
      ink: c("ink"),
      "ink-muted": c("ink-muted"),
      "ink-strong": c("ink-strong"),
      accent: c("accent"),
      "accent-hover": c("accent-hover"),
      "accent-soft": c("accent-soft"),
      warn: c("warn"),
      bad: c("bad"),
      focus: c("focus"),
      cert: {
        confirmed: c("cert-confirmed"),
        sure: c("cert-sure"),
        check: c("cert-check"),
        open: c("cert-open"),
      },
    },
    // "dot" only for small status dots; there is no pill radius.
    borderRadius: { none: "0", sm: "4px", DEFAULT: "6px", lg: "10px", dot: "9999px" },
    boxShadow: {
      none: "none",
      panel: "0 1px 2px rgb(0 0 0 / 0.04), 0 8px 24px rgb(0 0 0 / 0.08)", // floating list panel, popovers
      pop: "0 12px 32px rgb(0 0 0 / 0.12)", // dialogs, Cmd K
      kbd: "inset 0 -1px 0 rgb(0 0 0 / 0.08)",
    },
    fontFamily: {
      sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
    },
    fontWeight: { normal: "400", medium: "500", semibold: "600" }, // no 300, no 700
    fontSize: {
      micro: ["11px", { lineHeight: "14px" }], // kbd, map labels
      meta: ["12px", { lineHeight: "16px" }], // meta lines, labels
      ui: ["13px", { lineHeight: "18px" }], // list rows, buttons, inputs, body of the tool
      base: ["14px", { lineHeight: "20px" }], // field values, Begründung
      h3: ["15px", { lineHeight: "20px", fontWeight: "600" }],
      h2: ["18px", { lineHeight: "24px", fontWeight: "600", letterSpacing: "-0.01em" }],
      h1: ["24px", { lineHeight: "30px", fontWeight: "600", letterSpacing: "-0.02em" }],
      kpi: ["20px", { lineHeight: "24px", fontWeight: "600", letterSpacing: "-0.01em" }],
      hero: ["40px", { lineHeight: "44px", fontWeight: "600", letterSpacing: "-0.025em" }], // Nachweis numbers, compare years
    },
    extend: {
      maxWidth: { wrapper: "1520px" },
      transitionDuration: { hover: "200ms", fade: "350ms" },
      transitionTimingFunction: { calm: "cubic-bezier(0.2, 0.7, 0.3, 1)" }, // the owner's apps use this easing
    },
  },
  plugins: [animate],
};

export default config;
