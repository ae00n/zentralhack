// Review buttons with their key as a muted hint (FRONTPAGE_PLAN 5, review rule 2). Primary red only
// for Bestätigen / Speichern; the rest are secondary.

interface Props {
  editing: boolean;
  /** Already confirmed or corrected (here or on the server): Enter then only moves on. */
  decided: boolean;
  onConfirm: () => void;
  onCorrect: () => void;
  onSkip: () => void;
  onSave: () => void;
  onCancel: () => void;
}

const PRIMARY =
  "inline-flex items-center gap-2 rounded bg-accent px-4 py-2 font-bold text-white transition-colors duration-fade hover:bg-accent-hover";
const SECONDARY =
  "inline-flex items-center gap-2 rounded border border-rule bg-white px-4 py-2 font-bold text-ink-muted transition-colors duration-fade hover:text-ink-strong";

function Key({ k, light }: { k: string; light?: boolean }) {
  return <span className={`font-mono text-meta font-normal ${light ? "text-white/80" : "text-ink-muted"}`}>{k}</span>;
}

export default function ReviewBar({ editing, decided, onConfirm, onCorrect, onSkip, onSave, onCancel }: Props) {
  if (editing) {
    return (
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onSave} className={PRIMARY}>
          Speichern <Key k="⏎" light />
        </button>
        <button type="button" onClick={onCancel} className={SECONDARY}>
          Abbrechen <Key k="Esc" />
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      <button type="button" onClick={onConfirm} className={`${PRIMARY} flex-1 justify-center sm:flex-none`}>
        {decided ? "Weiter" : "Bestätigen"} <Key k="⏎" light />
      </button>
      <button type="button" onClick={onCorrect} className={SECONDARY}>
        Korrigieren <Key k="K" />
      </button>
      <button type="button" onClick={onSkip} className={`${SECONDARY} hidden sm:inline-flex`}>
        Überspringen <Key k="N" />
      </button>
    </div>
  );
}
