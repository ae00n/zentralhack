"use client";

// Upload (UPLOAD_PLAN step 2): drop zone for ZIPs, folders and images, plus a file and a folder picker.
// After reading, a preview: how many images, what was skipped and why, time and cost estimate, a name.
// "Analyse starten" creates the batch and opens it. Dropping again while the preview shows adds files.
import { FolderOpen, ImagePlus, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { buttonClass, FOCUS_RING } from "@/components/ui/button";
import { MODE, errorText, serverBatches } from "@/lib/api";
import { estimate, startBatch, suggestName } from "@/lib/batches";
import { cn } from "@/lib/cn";
import { collectImages, filesFromDrop, type Collected } from "@/lib/collect";

const THUMBS = 12;
const ACCEPT = ".zip,.jpg,.jpeg,.png,.tif,.tiff,.webp,application/zip,image/*";

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export default function UploadDrop({ className }: { className?: string }) {
  const router = useRouter();
  const [inputs, setInputs] = useState<File[]>([]);
  const [collected, setCollected] = useState<Collected | null>(null);
  const [reading, setReading] = useState(false);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  // null until known: the client runner needs this tab open until the batch is done.
  const [server, setServer] = useState<boolean | null>(null);
  const filePick = useRef<HTMLInputElement>(null);
  const folderPick = useRef<HTMLInputElement>(null);

  useEffect(() => {
    serverBatches().then(setServer, () => setServer(false));
    // React has no prop for it.
    folderPick.current?.setAttribute("webkitdirectory", "");
  }, []);

  const add = async (files: File[]) => {
    if (!files.length) return;
    const all = [...inputs, ...files];
    setInputs(all);
    setReading(true);
    setError(null);
    try {
      setCollected(await collectImages(all));
      if (!nameTouched) setName(suggestName(all));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setReading(false);
    }
  };

  const reset = () => {
    setInputs([]);
    setCollected(null);
    setName("");
    setNameTouched(false);
    setError(null);
  };

  const start = async () => {
    if (!collected?.images.length) return;
    setStarting(true);
    setError(null);
    try {
      const id = await startBatch(name.trim() || suggestName(inputs), collected.images, collected.skipped);
      router.push(`/stapel/${encodeURIComponent(id)}`);
    } catch (e) {
      setError(`Stapel konnte nicht angelegt werden: ${errorText(e)}`);
      setStarting(false);
    }
  };

  const thumbs = useMemo(
    () => (collected?.images ?? []).slice(0, THUMBS).map((p) => ({ name: p.file_name, url: URL.createObjectURL(p.file) })),
    [collected],
  );
  useEffect(() => () => thumbs.forEach((t) => URL.revokeObjectURL(t.url)), [thumbs]);

  const n = collected?.images.length ?? 0;
  const skipped = collected?.skipped ?? [];
  const est = estimate(n);

  return (
    <div className={className}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false);
        }}
        onDrop={async (e) => {
          e.preventDefault();
          setDragOver(false);
          await add(await filesFromDrop(e.dataTransfer));
        }}
        className={cn(
          "rounded-lg border border-dashed transition-colors duration-hover",
          dragOver ? "border-accent bg-accent-soft/[0.06]" : "border-rule/20 bg-paper-2/40",
          collected ? "p-4" : "px-4 py-10 sm:py-14",
        )}
      >
        {!collected ? (
          <div className="flex flex-col items-center text-center">
            <Upload size={28} strokeWidth={1.5} aria-hidden className="text-ink-muted" />
            <p className="mt-3 text-h3 text-ink">{reading ? "Lese Dateien ..." : "ZIP-Datei, Ordner oder Bilder hierher ziehen"}</p>
            <p className="mt-1 text-ui text-ink-muted">JPEG, PNG, TIFF oder WebP. Der Pfad im ZIP wird zum Dateinamen im Excel.</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <button type="button" onClick={() => filePick.current?.click()} disabled={reading} className={buttonClass("secondary")}>
                <ImagePlus size={14} strokeWidth={1.75} aria-hidden />
                Dateien wählen
              </button>
              <button type="button" onClick={() => folderPick.current?.click()} disabled={reading} className={buttonClass("secondary")}>
                <FolderOpen size={14} strokeWidth={1.75} aria-hidden />
                Ordner wählen
              </button>
            </div>
          </div>
        ) : (
          <div>
            {thumbs.length > 0 && (
              <ul className="flex gap-1.5 overflow-x-auto pb-1" aria-label="Vorschau">
                {thumbs.map((t) => (
                  <li key={t.name} className="h-14 w-20 shrink-0 overflow-hidden rounded-sm bg-paper-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={t.url} alt={t.name} title={t.name} className="h-full w-full object-cover" />
                  </li>
                ))}
                {n > THUMBS && (
                  <li className="flex h-14 shrink-0 items-center px-2 text-meta tnum text-ink-muted">+ {n - THUMBS} weitere</li>
                )}
              </ul>
            )}

            <p className="mt-3 text-h3 tnum text-ink" aria-live="polite">
              {reading ? "Lese Dateien ..." : plural(n, "Bild", "Bilder")}
              {skipped.length > 0 && <span className="font-normal text-ink-muted"> · {skipped.length} übersprungen</span>}
            </p>
            {n > 0 && (
              <p className="mt-1 text-ui tnum text-ink-muted">
                {MODE === "mock"
                  ? "Beispieldaten: keine echte Analyse, keine Kosten"
                  : `ca. ${est.minutes} Min. · ca. ${est.usd.toFixed(2)} USD · bereits analysierte Bilder kommen aus dem Cache und kosten nichts`}
              </p>
            )}
            {n === 0 && !reading && <p className="mt-1 text-ui text-bad">Keine Bilder gefunden.</p>}

            {skipped.length > 0 && (
              <details className="mt-3 text-ui">
                <summary className={cn("cursor-pointer rounded-sm text-ink-muted hover:text-ink", FOCUS_RING)}>
                  Übersprungene Dateien anzeigen
                </summary>
                <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
                  {skipped.map((s, i) => (
                    <li key={`${s.file_name}-${i}`} className="flex flex-wrap gap-x-2">
                      <span className="font-mono text-meta text-ink">{s.file_name}</span>
                      <span className="text-meta text-ink-muted">{s.reason}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <label className="mt-4 block max-w-[420px]">
              <span className="text-meta font-medium text-ink-muted">Name des Stapels</span>
              <input
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setNameTouched(true);
                }}
                className="mt-1 h-8 w-full rounded border border-rule/[0.12] bg-paper px-2 text-base text-ink outline-none focus-visible:ring-2 focus-visible:ring-focus/50"
              />
            </label>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button type="button" onClick={start} disabled={!n || reading || starting} className={buttonClass("primary")}>
                {starting ? "Lege Stapel an ..." : "Analyse starten"}
              </button>
              <button type="button" onClick={() => filePick.current?.click()} disabled={reading || starting} className={buttonClass("secondary")}>
                Weitere Dateien
              </button>
              <button type="button" onClick={reset} disabled={starting} className={buttonClass("ghost")}>
                Verwerfen
              </button>
            </div>
            {server === false && n > 0 && (
              <p className="mt-3 text-meta text-ink-muted">Dieses Fenster bitte offen lassen, bis die Analyse fertig ist.</p>
            )}
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-ui text-bad">{error}</p>}

      <input
        ref={filePick}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          void add(Array.from(e.target.files ?? []));
          e.target.value = ""; // the same file can be picked again
        }}
      />
      <input
        ref={folderPick}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          void add(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </div>
  );
}
