import Link from "next/link";
import { MODE } from "@/lib/api";

// sz.ch-style header row (FRONTPAGE_PLAN 2.2). Never the Kanton Schwyz shield or wordmark (licence).
function Tag({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-5 items-center rounded bg-paper-2 px-1.5 text-[11px] ${className}`}>{children}</span>
  );
}

export default function SiteHeader() {
  return (
    <header className="bg-paper">
      <div className="wrapper flex min-h-14 flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2 md:min-h-[72px]">
        <Link href="/" className="text-body hover:text-ink-strong md:text-h3 md:font-normal">
          Staatsarchiv Schwyz
          <span className="block font-light text-ink-muted sm:inline">
            <span className="hidden sm:inline"> · </span>Erschliessungs-Assistent
          </span>
        </Link>
        <nav className="flex items-center gap-5 text-small text-ink-muted">
          <Link href="/nachweis" className="hover:text-ink-strong">
            Nachweis
          </Link>
          <Link href="/nachweis#methode" className="hover:text-ink-strong">
            Methode
          </Link>
          <Tag>Prototyp</Tag>
          {MODE === "mock" && <Tag className="text-warn">Beispieldaten</Tag>}
        </nav>
      </div>
    </header>
  );
}
