// Footer line required by FRONTPAGE_PLAN 2 (licence): prototype, not an official service of the canton.
export default function SiteFooter() {
  return (
    <footer className="mt-12 border-t-2 border-rule bg-paper-2">
      <p className="wrapper py-6 text-small text-ink-muted">
        Prototyp für das Staatsarchiv Schwyz, Zentral Hack 2026. Kein offizielles Angebot des Kantons Schwyz.
        {" · "}Karten © swisstopo{" · "}Fotos © Staatsarchiv Schwyz, nicht zur Weiterverbreitung
      </p>
    </footer>
  );
}
