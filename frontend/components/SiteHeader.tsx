"use client";

// Shell (FRONTPAGE_POLISH 4, item 2): a 2px red strip and a 52px white header. Wordmark, readable
// Prototyp tag, search field (⌘K / Ctrl+K focuses it), Nachweis, and the Excel button. Never the
// Kanton Schwyz shield or wordmark (licence). Phone: the links sit behind a menu button.
import { Download, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import Kbd from "@/components/ui/Kbd";
import { MODE, exportXlsxUrl } from "@/lib/api";

function Tag({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-5 items-center rounded-sm bg-paper-2 px-1.5 text-micro font-medium text-ink-muted ${className}`}>
      {children}
    </span>
  );
}

const FOCUS = "outline-none focus-visible:ring-2 focus-visible:ring-focus/50 focus-visible:ring-offset-1 focus-visible:ring-offset-paper";

/** Header search: filters the desk list via ?q= (the ⌘K palette replaces it in polish item 9). */
function SearchField({ className = "" }: { className?: string }) {
  const router = useRouter();
  const current = useSearchParams().get("q") ?? "";
  const [q, setQ] = useState(current);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => setQ(current), [current]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        const v = q.trim();
        router.push(v ? `/?q=${encodeURIComponent(v)}` : "/");
      }}
      className={`flex h-8 items-center gap-2 rounded border border-rule/[0.12] bg-paper px-2.5 text-ui text-ink-muted transition-colors duration-hover focus-within:border-rule/20 focus-within:ring-2 focus-within:ring-focus/50 hover:border-rule/20 ${className}`}
    >
      <Search size={14} strokeWidth={1.75} aria-hidden className="shrink-0" />
      <input
        ref={input}
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Signatur, Ort oder Gebäude suchen"
        aria-label="Signatur, Ort oder Gebäude suchen"
        className="h-full min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-muted"
      />
      <Kbd>⌘K</Kbd>
    </form>
  );
}

export default function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <div className="sticky top-0 z-30">
      <div className="h-[2px] bg-accent" aria-hidden />
      <header className="flex h-[52px] items-center gap-4 border-b border-rule/[0.08] bg-paper/85 px-4 backdrop-blur-md">
        <Link href="/" className={`flex min-w-0 items-center gap-2 rounded-sm ${FOCUS}`}>
          <span className="truncate text-ui">
            <span className="font-semibold text-ink">Staatsarchiv Schwyz</span>
            <span className="hidden text-ink-muted sm:inline"> · Erschliessung</span>
          </span>
          <Tag>Prototyp</Tag>
          {MODE === "mock" && <Tag className="hidden text-warn sm:inline-flex">Beispieldaten</Tag>}
        </Link>

        <Suspense fallback={<div className="hidden h-8 w-[320px] md:block" />}>
          <SearchField className="hidden w-[320px] md:flex" />
        </Suspense>

        <nav className="ml-auto hidden items-center gap-1 sm:flex">
          <Link
            href="/nachweis"
            className={`inline-flex h-8 items-center rounded px-2 text-ui text-ink-muted transition-colors duration-hover hover:bg-paper-2 hover:text-ink ${FOCUS}`}
          >
            Nachweis
          </Link>
          <a
            href={exportXlsxUrl()}
            download
            className={`inline-flex h-8 items-center gap-1.5 rounded bg-accent px-3 text-ui font-medium text-white transition-colors duration-hover hover:bg-accent-hover active:translate-y-px ${FOCUS}`}
          >
            <Download size={14} strokeWidth={1.75} aria-hidden />
            Excel herunterladen
          </a>
        </nav>

        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="phone-menu"
          aria-label={open ? "Menü schliessen" : "Menü öffnen"}
          className={`ml-auto rounded p-1.5 text-ink-muted hover:bg-paper-2 hover:text-ink sm:hidden ${FOCUS}`}
        >
          {open ? <X size={20} strokeWidth={1.5} /> : <Menu size={20} strokeWidth={1.5} />}
        </button>
      </header>

      {open && (
        <nav id="phone-menu" className="fade-in border-b border-rule/[0.08] bg-paper sm:hidden">
          <div className="space-y-2 px-4 py-3">
            <Suspense>
              <SearchField className="w-full" />
            </Suspense>
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
