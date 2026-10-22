import Link from "next/link";
import { MODE } from "@/lib/api";

export default function SiteHeader() {
  return (
    <header className="border-b border-rule">
      <div className="mx-auto flex max-w-[1440px] items-baseline justify-between gap-4 px-4 py-4 md:px-8">
        <Link href="/" className="font-serif text-section hover:text-accent">
          Zeitreise Schwyz
        </Link>
        <nav className="flex items-baseline gap-6 text-body">
          <Link href="/" className="hover:text-accent">
            Archiv
          </Link>
          {MODE === "mock" && <span className="font-mono text-meta text-warn">Beispieldaten</span>}
        </nav>
      </div>
    </header>
  );
}
