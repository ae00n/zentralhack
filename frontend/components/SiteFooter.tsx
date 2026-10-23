"use client";

// Compact footer (FRONTPAGE_POLISH 4): one muted line with the three facts. Not on the desk, which must
// fit one viewport; the Prototyp tag in the header stays visible there.
import { usePathname } from "next/navigation";

export default function SiteFooter() {
  if (usePathname() === "/") return null;
  return (
    <footer className="border-t border-rule/[0.08]">
      <p className="px-4 py-3 text-meta text-ink-muted">
        Prototyp für das Staatsarchiv Schwyz, Zentral Hack 2026. Kein offizielles Angebot des Kantons Schwyz.
        {" · "}Karten © swisstopo{" · "}Fotos © Staatsarchiv Schwyz, nicht zur Weiterverbreitung
      </p>
    </footer>
  );
}
