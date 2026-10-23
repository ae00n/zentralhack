"use client";

// Export (build step 6): "CSV herunterladen" / "JSON herunterladen", on the result and on the Archiv.
import { useState } from "react";
import { downloadExport, errorText, type ExportFormat } from "@/lib/api";

const FORMATS: { format: ExportFormat; label: string }[] = [
  { format: "csv", label: "CSV herunterladen" },
  { format: "json", label: "JSON herunterladen" },
];

/** ids undefined = every analysed photo. */
export default function ExportButtons({ ids, className = "" }: { ids?: string[]; className?: string }) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const run = async (format: ExportFormat) => {
    setBusy(format);
    setNote(null);
    try {
      const rows = await downloadExport(format, ids);
      if (rows === 0) setNote(ids?.length ? "Für die Auswahl liegt keine Analyse vor." : "Noch keine Analysen vorhanden.");
    } catch (e) {
      setNote(`Export fehlgeschlagen: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={className}>
      <div className="flex flex-wrap gap-2">
        {FORMATS.map(({ format, label }) => (
          <button
            key={format}
            type="button"
            onClick={() => run(format)}
            disabled={busy !== null}
            className="rounded border border-rule px-3 py-1.5 text-meta hover:border-ink disabled:text-ink-muted"
          >
            {busy === format ? "Exportiere ..." : label}
          </button>
        ))}
      </div>
      {note && <p className="mt-1.5 text-meta text-ink-muted">{note}</p>}
    </div>
  );
}
