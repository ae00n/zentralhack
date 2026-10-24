// Review buttons with their key as a Kbd hint (FRONTPAGE_POLISH 4 + 6): Bestätigen primary (red),
// Korrigieren secondary, Überspringen ghost; while editing Speichern / Abbrechen.
import { buttonClass } from "@/components/ui/button";
import Kbd from "@/components/ui/Kbd";

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

export default function ReviewBar({ editing, decided, onConfirm, onCorrect, onSkip, onSave, onCancel }: Props) {
  if (editing) {
    return (
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onSave} className={buttonClass("primary")}>
          Speichern <Kbd onAccent>⏎</Kbd>
        </button>
        <button type="button" onClick={onCancel} className={buttonClass("secondary")}>
          Abbrechen <Kbd>Esc</Kbd>
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      <button type="button" onClick={onConfirm} className={buttonClass("primary", "flex-1 sm:flex-none")}>
        {decided ? "Weiter" : "Bestätigen"} <Kbd onAccent>⏎</Kbd>
      </button>
      <button type="button" onClick={onCorrect} className={buttonClass("secondary")}>
        Korrigieren <Kbd>K</Kbd>
      </button>
      <button type="button" onClick={onSkip} className={buttonClass("ghost", "hidden sm:inline-flex")}>
        Überspringen <Kbd>N</Kbd>
      </button>
    </div>
  );
}
