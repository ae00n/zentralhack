import type { Config } from "tailwindcss";

// Archive look (docs/SCOPE_3_FRONTEND.md). Values live as CSS variables in app/globals.css.
// The theme is deliberately narrow: no rounded-full, no bold above 600, no shadows.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      paper: "var(--paper)",
      "paper-2": "var(--paper-2)",
      rule: "var(--rule)",
      ink: "var(--ink)",
      "ink-muted": "var(--ink-muted)",
      accent: "var(--accent)",
      warn: "var(--warn)",
      bad: "var(--bad)",
    },
    borderRadius: {
      none: "0",
      DEFAULT: "2px",
    },
    boxShadow: {
      none: "none",
    },
    fontWeight: {
      normal: "400",
      medium: "500",
      semibold: "600",
    },
    extend: {
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        meta: ["12px", "16px"],
        body: ["14px", "20px"],
        section: ["18px", "24px"],
        page: ["28px", "34px"],
      },
      transitionDuration: {
        fade: "400ms",
      },
    },
  },
  plugins: [],
};

export default config;
