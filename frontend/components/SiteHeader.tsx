"use client";

// Shell (FRONTPAGE_POLISH 4, item 2): a 2px red strip and a 52px white header. Wordmark, readable
// Prototyp tag, Nachweis, and the Excel button. Never the Kanton Schwyz shield or wordmark (licence).
// UPLOAD_PLAN step 2: the step strip Hochladen > Analyse > Prüfen > Export replaces the search field
// (the search moved into the desk panel). Phone: the current step as text, the links behind a menu button.
// "Foto hochladen" top right (Timo, 24.10.): one photo goes straight to the live view. The desk is the main
// page (step 2b), so step 1 Hochladen opens the file picker instead of a page.
import { ChevronRight, Download, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { MODE, exportXlsxUrl } from "@/lib/api";
import { batchCounts, batchExportUrl, isRunning, useBatches } from "@/lib/batches";
import QuickUpload, { OPEN_UPLOAD } from "@/components/upload/QuickUpload";
import { cn } from "@/lib/cn";
import { deskHref } from "@/lib/format";

function Tag({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-5 items-center rounded-sm bg-paper-2 px-1.5 text-micro font-medium text-ink-muted ${className}`}>
      {children}
    </span>
  );
}

const FOCUS = "outline-none focus-visible:ring-2 focus-visible:ring-focus/50 focus-visible:ring-offset-1 focus-visible:ring-offset-paper";

const STEPS = ["Hochladen", "Analyse", "Prüfen", "Export"] as const;

interface Flow {
  /** 1..4, null outside the flow (Nachweis). */
  step: number | null;
  /** Where Analyse / Prüfen lead: the batch of this page. */
  batchHref: string | null;
  excelUrl: string | null;
}

/** The flow step of the current page. Step 4 becomes the export dialog in UPLOAD_PLAN step 5. */
function useFlow(): Flow {
  const path = usePathname();
  const { batches } = useBatches();
  if (path === "/") return { step: 3, batchHref: deskHref(), excelUrl: exportXlsxUrl() };
  const m = path.match(/^\/stapel\/([^/]+)/);
  if (m) {
    const id = decodeURIComponent(m[1]);
    if (id === "challenge") return { step: 3, batchHref: deskHref(), excelUrl: exportXlsxUrl() };
    const b = batches.find((x) => x.id === id);
    return { step: b && isRunning(b) ? 2 : 3, batchHref: path, excelUrl: b && batchCounts(b).done ? batchExportUrl(b) : null };
  }
  // The photo view does not know its batch yet (UPLOAD_PLAN step 4): it belongs to SG.CIV.17 for now.
  if (path.startsWith("/analyse/")) return { step: 3, batchHref: deskHref(), excelUrl: exportXlsxUrl() };
  return { step: null, batchHref: null, excelUrl: exportXlsxUrl() };
}

function StepStrip({ flow }: { flow: Flow }) {
  const target = (n: number) => (n === 1 ? null : n === 4 ? flow.excelUrl : flow.batchHref);
  return (
    <ol aria-label="Ablauf" className="hidden h-full items-stretch gap-1 md:flex">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const current = flow.step === n;
        const passed = flow.step !== null && n < flow.step;
        const href = target(n);
        const body = (
          <>
            <span className="tnum text-meta">{n}</span>
            {label}
          </>
        );
        const cls = cn(
          "inline-flex items-center gap-1.5 border-b-2 px-1.5 text-ui transition-colors duration-hover",
          current ? "border-accent font-medium text-ink" : "border-transparent",
          !current && (passed ? "text-ink" : "text-ink-muted"),
          href && !current && "hover:text-ink",
          FOCUS,
        );
        return (
          <li key={label} className="flex items-stretch">
            {i > 0 && <ChevronRight size={12} strokeWidth={1.75} aria-hidden className="mr-1 self-center text-ink-muted" />}
            {n === 1 && !current ? (
              <button type="button" onClick={() => window.dispatchEvent(new Event(OPEN_UPLOAD))} className={cn(cls, "hover:text-ink")}>
                {body}
              </button>
            ) : !href || current ? (
              <span className={cls} aria-current={current ? "step" : undefined}>
                {body}
              </span>
            ) : n === 4 ? (
              <a href={href} download className={cls}>
                {body}
              </a>
            ) : (
              <Link href={href} className={cls}>
                {body}
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default function SiteHeader() {
  const [open, setOpen] = useState(false);
  const flow = useFlow();
  return (
    <div className="sticky top-0 z-30">
      <div className="h-[2px] bg-accent" aria-hidden />
      <header className="flex h-[52px] items-center gap-4 border-b border-rule/[0.08] bg-paper/85 px-4 backdrop-blur-md">
        <Link href="/" className={`flex min-w-0 items-center gap-2 rounded-sm ${FOCUS}`}>
          <span className="truncate text-ui">
            <span className="font-semibold text-ink">Staatsarchiv Schwyz</span>
            <span className="hidden text-ink-muted lg:inline"> · Erschliessung</span>
          </span>
          <Tag>Prototyp</Tag>
          {MODE === "mock" && <Tag className="hidden text-warn sm:inline-flex">Beispieldaten</Tag>}
        </Link>

        <StepStrip flow={flow} />

        <nav className="ml-auto hidden items-center gap-1 sm:flex">
          <QuickUpload className="mr-1" />
          <Link
            href="/nachweis"
            className={`inline-flex h-8 items-center rounded px-2 text-ui text-ink-muted transition-colors duration-hover hover:bg-paper-2 hover:text-ink ${FOCUS}`}
          >
            Nachweis
          </Link>
          {flow.excelUrl && (
            <a
              href={flow.excelUrl}
              download
              className={`inline-flex h-8 items-center gap-1.5 rounded bg-accent px-3 text-ui font-medium text-white transition-colors duration-hover hover:bg-accent-hover active:translate-y-px ${FOCUS}`}
            >
              <Download size={14} strokeWidth={1.75} aria-hidden />
              Excel herunterladen
            </a>
          )}
        </nav>

        {flow.step !== null && (
          <span className="ml-auto text-meta tnum text-ink-muted sm:ml-0 md:hidden">
            {flow.step}/4 · {STEPS[flow.step - 1]}
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="phone-menu"
          aria-label={open ? "Menü schliessen" : "Menü öffnen"}
          className={cn("rounded p-1.5 text-ink-muted hover:bg-paper-2 hover:text-ink sm:hidden", flow.step === null && "ml-auto", FOCUS)}
        >
          {open ? <X size={20} strokeWidth={1.5} /> : <Menu size={20} strokeWidth={1.5} />}
        </button>
      </header>

      {open && (
        <nav id="phone-menu" className="fade-in border-b border-rule/[0.08] bg-paper sm:hidden">
          <div className="space-y-2 px-4 py-3">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                window.dispatchEvent(new Event(OPEN_UPLOAD));
              }}
              className={`block rounded py-1.5 text-ui font-medium ${FOCUS}`}
            >
              Foto hochladen
            </button>
            <Link href="/nachweis" onClick={() => setOpen(false)} className={`block rounded py-1.5 text-ui font-medium ${FOCUS}`}>
              Nachweis
            </Link>
            {MODE === "mock" && <Tag className="text-warn">Beispieldaten</Tag>}
          </div>
        </nav>
      )}
    </div>
  );
}
