"use client";

// The one big red surface (sz.ch search band, FRONTPAGE_PLAN 2.2). Submitting opens the desk with ?q=;
// the desk list filters on it (build item 4).
import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SearchBand() {
  const router = useRouter();
  const [q, setQ] = useState("");

  return (
    <div className="bg-accent">
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const v = q.trim();
          router.push(v ? `/?q=${encodeURIComponent(v)}` : "/");
        }}
        className="wrapper flex h-[52px] items-center gap-3 md:h-16"
      >
        <Search size={22} strokeWidth={1.5} className="shrink-0 text-white" aria-hidden />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Signatur, Ort oder Gebäude suchen"
          aria-label="Signatur, Ort oder Gebäude suchen"
          className="search-band-input w-full border-0 border-b border-accent-light bg-transparent py-1 text-[18px] font-normal text-white md:text-[22px]"
        />
      </form>
    </div>
  );
}
