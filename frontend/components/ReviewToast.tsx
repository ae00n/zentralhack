"use client";

// Undo toast (FRONTPAGE_PLAN 5, review rule 6): "Bestätigt: SG.CIV.17.3 · Rückgängig (⌫)", fades after 6 s.
import { undo, useReviewStore } from "@/lib/reviewQueue";

export default function ReviewToast() {
  const { toast } = useReviewStore();
  if (!toast) return null;
  return (
    <div
      role="status"
      className={`fade-in fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded px-4 py-2.5 text-ui text-white ${toast.error ? "bg-bad" : "bg-ink"}`}
    >
      <span>{toast.text}</span>
      {toast.undoable && (
        <button type="button" onClick={() => undo()} className="font-semibold underline hover:text-white/80">
          Rückgängig (⌫)
        </button>
      )}
    </div>
  );
}
