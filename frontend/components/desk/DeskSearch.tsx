"use client";

// Search over the desk list via ?q=; ⌘K / Ctrl+K focuses it. It sat in the header until UPLOAD_PLAN step 2,
// where the header got the step strip. Must render inside a Suspense boundary (useSearchParams).
import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Kbd from "@/components/ui/Kbd";
import { cn } from "@/lib/cn";
import { deskHref } from "@/lib/format";

export default function DeskSearch({ className }: { className?: string }) {
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
        router.push(deskHref({ q: q.trim() }));
      }}
      className={cn(
        "flex h-8 items-center gap-2 rounded border border-rule/[0.12] bg-paper px-2.5 text-ui text-ink-muted transition-colors duration-hover focus-within:border-rule/20 focus-within:ring-2 focus-within:ring-focus/50 hover:border-rule/20",
        className,
      )}
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
