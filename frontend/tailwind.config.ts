import type { Config } from "tailwindcss";

// sz.ch family look (docs/FRONTPAGE_PLAN.md section 2.1). Values live as CSS variables in app/globals.css.
// The theme replaces Tailwind's defaults on purpose: radius stops at 4px (no pills), no shadows
// except the focus ring, one brand red.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#fff",
      paper: "var(--paper)",
      "paper-2": "var(--paper-2)",
      rule: "var(--rule)",
      ink: "var(--ink)",
      "ink-muted": "var(--ink-muted)",
      "ink-strong": "var(--ink-strong)",
      accent: "var(--accent)",
      "accent-hover": "var(--accent-hover)",
      "accent-dark": "var(--accent-dark)",
      "accent-light": "var(--accent-light)",
      warn: "var(--warn)",
      bad: "var(--bad)",
      cert: {
        confirmed: "var(--cert-confirmed)",
        sure: "var(--cert-sure)",
        check: "var(--cert-check)",
        open: "var(--cert-open)",
      },
    },
    borderRadius: {
      none: "0",
      DEFAULT: "4px",
    },
    boxShadow: {
      none: "none",
      focus: "0 0 0 4px var(--focus-ring)",
    },
    fontFamily: {
      sans: ["var(--font-barlow)", "Helvetica", "Arial", "sans-serif"],
      mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
    },
    fontWeight: {
      light: "300",
      normal: "400",
      medium: "500",
      bold: "700",
    },
    fontSize: {
      meta: ["13px", { lineHeight: "18px" }],
      small: ["14px", { lineHeight: "20px" }],
      body: ["16px", { lineHeight: "24px" }],
      h3: ["18px", { lineHeight: "24px", fontWeight: "700" }],
      h2: ["24px", { lineHeight: "30px", fontWeight: "700" }],
      page: ["40px", { lineHeight: "48px", fontWeight: "300" }], // phone: text-[30px]
      counter: ["32px", { lineHeight: "36px", fontWeight: "300" }],
    },
    extend: {
      maxWidth: {
        wrapper: "1520px", // sz .wrapper: 92% wide, max 1520
      },
      transitionDuration: {
        fade: "400ms",
      },
    },
  },
  plugins: [],
};

export default config;
