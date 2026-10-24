"use client";

// Batch cards on the start page (UPLOAD_PLAN step 2): SG.CIV.17 first (processed before the event, opens
// the desk), then the uploaded batches, newest first, with progress. Removing a batch only forgets it in
// this browser.
import { X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { FOCUS_RING } from "@/components/ui/button";
import { imageUrl, listChallenge } from "@/lib/api";
import { batchCounts, isRunning, removeBatch, useBatches } from "@/lib/batches";
import { cn } from "@/lib/cn";
import { deskHref } from "@/lib/format";
import type { Batch, PhotoRecord } from "@/lib/types";

const CARD = cn(
  "group flex min-w-0 gap-3 rounded-lg border border-rule/[0.08] bg-paper p-3 transition-colors duration-hover hover:border-rule/20 hover:bg-paper-2/40",
  FOCUS_RING,
);

function Thumb({ src }: { src: string | null }) {
  return (
    <div className="h-16 w-24 shrink-0 overflow-hidden rounded-sm bg-paper-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src && <img src={src} alt="" className="h-full w-full object-cover" />}
    </div>
  );
}

function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : `${d.toLocaleDateString("de-CH")} ${d.toLocaleTimeString("de-CH", { hour: "2-digit", minute: "2-digit" })}`;
}

function ChallengeCard() {
  const [records, setRecords] = useState<PhotoRecord[] | null>(null);
  useEffect(() => {
    listChallenge().then(setRecords, () => setRecords([]));
  }, []);
  const prio = records?.filter((r) => r.raw?.priority === 1) ?? [];
  const first = prio[0] ?? records?.[0];
  return (
    <Link href={deskHref()} className={CARD}>
      <Thumb src={first ? imageUrl(first.id, 240) : null} />
      <div className="min-w-0">
        <p className="truncate text-h3 text-ink group-hover:text-accent">SG.CIV.17</p>
        <p className="mt-0.5 text-meta tnum text-ink-muted">
          {records ? `${records.length} Fotos · ${prio.length} Prio 1` : "Lade ..."}
        </p>
        <p className="mt-1 text-meta text-ink-muted">Beispiel: bereits verarbeitet</p>
      </div>
    </Link>
  );
}

function BatchCard({ batch }: { batch: Batch }) {
  const c = batchCounts(batch);
  const work = c.total - c.skipped;
  const finished = c.done + c.error;
  const running = isRunning(batch);
  const firstDone = batch.items.find((i) => i.status === "done" && i.photo_id);
  const state = running ? "läuft" : c.error ? "mit Fehlern" : "fertig";
  return (
    <div className="relative">
      <Link href={`/stapel/${encodeURIComponent(batch.id)}`} className={CARD}>
        <Thumb src={firstDone?.photo_id ? imageUrl(firstDone.photo_id, 240) : null} />
        <div className="min-w-0 flex-1 pr-6">
          <p className="truncate text-h3 text-ink group-hover:text-accent">{batch.name}</p>
          <p className="mt-0.5 text-meta tnum text-ink-muted">
            {work} Bilder · {c.done} fertig{c.error > 0 && ` · ${c.error} Fehler`}
          </p>
          <p className="mt-1 text-meta tnum text-ink-muted">
            {when(batch.created_at)} · <span className={cn(running && "text-ink", c.error > 0 && !running && "text-warn")}>{state}</span>
          </p>
          {running && (
            <div className="mt-2 h-0.5 w-full overflow-hidden rounded-sm bg-paper-2" aria-hidden>
              <div className="h-full bg-ink/60 transition-[width] duration-fade" style={{ width: `${work ? (finished / work) * 100 : 0}%` }} />
            </div>
          )}
        </div>
      </Link>
      <button
        type="button"
        onClick={() => {
          if (window.confirm(`Stapel «${batch.name}» aus dieser Liste entfernen? Die Ergebnisse bleiben im Backend.`)) removeBatch(batch.id);
        }}
        aria-label={`Stapel ${batch.name} entfernen`}
        title="Entfernen"
        className={cn("absolute right-2 top-2 rounded p-1 text-ink-muted hover:bg-paper-2 hover:text-ink", FOCUS_RING)}
      >
        <X size={14} strokeWidth={1.75} />
      </button>
    </div>
  );
}

export default function BatchCards() {
  const { batches, ready } = useBatches();
  return (
    <div>
      <ul className="grid gap-3 sm:grid-cols-2">
        <li>
          <ChallengeCard />
        </li>
        {batches.map((b) => (
          <li key={b.id}>
            <BatchCard batch={b} />
          </li>
        ))}
      </ul>
      {ready && batches.length === 0 && <p className="mt-3 text-ui text-ink-muted">Noch keine eigenen Stapel.</p>}
    </div>
  );
}
