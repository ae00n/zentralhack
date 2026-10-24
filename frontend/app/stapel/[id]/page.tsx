"use client";

// A batch (UPLOAD_PLAN step 2). "challenge" is SG.CIV.17, processed before the event: the desk as before.
// An upload of one photo opens the live view (map flight, Timo 24.10.), several photos the grid.
import { useParams } from "next/navigation";
import BatchView from "@/components/batch/BatchView";
import Arbeitsplatz from "@/components/desk/Arbeitsplatz";
import LiveDesk from "@/components/live/LiveDesk";
import { getBatch, useBatches } from "@/lib/batches";

function Upload({ id }: { id: string }) {
  useBatches();
  const batch = getBatch(id);
  const single = batch && batch.items.filter((i) => i.status !== "skipped").length === 1;
  // Keyed: "Weiteres Foto" moves from one live batch to the next, which must start fresh.
  return single ? <LiveDesk key={batch.id} batch={batch} /> : <BatchView id={id} />;
}

export default function StapelPage() {
  const id = decodeURIComponent(String(useParams<{ id: string }>().id));
  return id === "challenge" ? <Arbeitsplatz /> : <Upload id={id} />;
}
