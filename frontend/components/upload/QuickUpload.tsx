"use client";

// "Foto hochladen" in the header (Timo, 24.10.): pick or drop files anywhere and they start at once, no
// preview. One image opens the live view (map flight when the place is found), several open the batch
// grid. A drop on the start page's own drop zone is left to that zone (it calls preventDefault).
// Other components open the picker with window.dispatchEvent(new Event(OPEN_UPLOAD)).
import { Upload } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { buttonClass } from "@/components/ui/button";
import { errorText } from "@/lib/api";
import { startBatch, suggestName } from "@/lib/batches";
import { cn } from "@/lib/cn";
import { collectImages, filesFromDrop } from "@/lib/collect";

export const OPEN_UPLOAD = "open-upload";
const ACCEPT = ".zip,.jpg,.jpeg,.png,.tif,.tiff,.webp,application/zip,image/*";

function hasFiles(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

export default function QuickUpload({ className }: { className?: string }) {
  const router = useRouter();
  // The start page has its own drop zone with a preview; no "starts at once" overlay there.
  const onStart = usePathname() === "/";
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const go = async (files: File[]) => {
    if (!files.length || busy) return;
    setBusy(true);
    try {
      const { images, skipped } = await collectImages(files);
      if (!images.length) {
        toast.error(skipped[0] ? `Kein Bild gefunden: ${skipped[0].reason}` : "Kein Bild gefunden");
        return;
      }
      const name = images.length === 1 ? images[0].file_name.slice(images[0].file_name.lastIndexOf("/") + 1) : suggestName(files);
      const id = await startBatch(name, images, skipped);
      router.push(`/stapel/${encodeURIComponent(id)}`);
    } catch (e) {
      toast.error(`Hochladen fehlgeschlagen: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  const latest = useRef(go);
  latest.current = go;

  useEffect(() => {
    // dragenter / dragleave fire for every child; count them to know when the files left the window.
    let depth = 0;
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth++;
      setDragging(true);
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (!depth) setDragging(false);
    };
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault(); // allows the drop
    };
    const drop = async (e: DragEvent) => {
      depth = 0;
      setDragging(false);
      if (!hasFiles(e) || e.defaultPrevented) return; // the start page's drop zone handled it
      e.preventDefault();
      if (e.dataTransfer) await latest.current(await filesFromDrop(e.dataTransfer));
    };
    const open = () => input.current?.click();
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    window.addEventListener(OPEN_UPLOAD, open);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
      window.removeEventListener(OPEN_UPLOAD, open);
    };
  }, []);

  return (
    <>
      <button type="button" onClick={() => input.current?.click()} disabled={busy} className={buttonClass("secondary", className)}>
        <Upload size={14} strokeWidth={1.75} aria-hidden />
        {busy ? "Lese ..." : "Foto hochladen"}
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        aria-hidden
        tabIndex={-1}
        onChange={(e) => {
          void go(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      {dragging && !onStart && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-ink/20 p-6 backdrop-blur-[2px]">
          <div className={cn("rounded-lg border-2 border-dashed border-accent bg-paper px-8 py-6 text-center shadow-pop")}>
            <Upload size={28} strokeWidth={1.5} aria-hidden className="mx-auto text-accent" />
            <p className="mt-2 text-h3 text-ink">Foto loslassen</p>
            <p className="mt-1 text-ui text-ink-muted">Die Analyse startet sofort.</p>
          </div>
        </div>
      )}
    </>
  );
}
