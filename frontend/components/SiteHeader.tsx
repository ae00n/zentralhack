"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { MODE } from "@/lib/api";

// sz.ch-style header row (FRONTPAGE_PLAN 2.2). Never the Kanton Schwyz shield or wordmark (licence).
// Phone (plan 4): "Staatsarchiv Schwyz [Prototyp]" / "Erschliessungs-Assistent [=]", links behind the menu.
function Tag({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-5 items-center rounded bg-paper-2 px-1.5 text-[11px] ${className}`}>{children}</span>
  );
}

const LINKS = [
  { href: "/nachweis", label: "Nachweis" },
  { href: "/nachweis#methode", label: "Methode" },
];

export default function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="bg-paper">
      <div className="wrapper flex min-h-14 items-center justify-between gap-x-6 py-2 md:min-h-[72px]">
        <Link href="/" className="text-body hover:text-ink-strong md:text-h3 md:font-normal">
          <span className="flex items-center gap-2">
            Staatsarchiv Schwyz
            <Tag className="sm:hidden">Prototyp</Tag>
          </span>
          <span className="block font-light text-ink-muted sm:inline">
            <span className="hidden sm:inline"> · </span>Erschliessungs-Assistent
          </span>
        </Link>
        <nav className="hidden items-center gap-5 text-small text-ink-muted sm:flex">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-ink-strong">
              {l.label}
            </Link>
          ))}
          <Tag>Prototyp</Tag>
          {MODE === "mock" && <Tag className="text-warn">Beispieldaten</Tag>}
        </nav>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="phone-menu"
          aria-label={open ? "Menü schliessen" : "Menü öffnen"}
          className="rounded p-1.5 text-ink-muted hover:text-ink-strong sm:hidden"
        >
          {open ? <X size={22} strokeWidth={1.5} /> : <Menu size={22} strokeWidth={1.5} />}
        </button>
      </div>
      {open && (
        <nav id="phone-menu" className="fade-in border-t border-rule bg-paper-2 sm:hidden">
          <ul className="wrapper py-2">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} onClick={() => setOpen(false)} className="block py-2 font-bold hover:text-ink-strong">
                  {l.label}
                </Link>
              </li>
            ))}
            {MODE === "mock" && (
              <li className="py-2">
                <Tag className="text-warn">Beispieldaten</Tag>
              </li>
            )}
          </ul>
        </nav>
      )}
    </header>
  );
}
