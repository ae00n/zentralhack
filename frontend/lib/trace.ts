// The agent's steps in short (Said, 24.10., for the pitch): one line per step, the long text only on demand.
// v7 writes a fixed set of steps (web search, three attempts, image check, judge, final); older runs and
// uploads use the tool names in lib/labels.ts and get a first-sentence summary.
import { toolLabel } from "@/lib/labels";
import type { TraceItem } from "@/lib/types";

export interface StepView {
  label: string;
  /** The one line shown. */
  short: string;
  /** The full text behind "mehr", when the short line leaves something out. */
  detail: string | null;
  /** Image check: points per place, best first. */
  bars: { name: string; points: number }[] | null;
  final: boolean;
}

const ATTEMPT: Record<string, string> = {
  "attempt:all": "Versuch 1 · alle Hinweise",
  "attempt:web": "Versuch 2 · mit Websuche",
  "attempt:blind": "Versuch 3 · nur das Bild",
};

const SHORT_MAX = 150;
// A full stop after these is not the end of a sentence ("St. Anna", "ehem. Grand Hotel").
const ABBREV = /(?:^|\s)(?:St|ca|Nr|ehem|bzw|vgl|evtl|z\.B|u\.a|Str)$/i;

/** First sentence of a text, and the rest (or null when the sentence is the whole text). */
export function firstSentence(text: string): { head: string; rest: string | null } {
  const t = text.replace(/\*\*/g, "").trim();
  const re = /[.!?](?=\s+[A-ZÄÖÜ«"(])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(t))) {
    if (ABBREV.test(t.slice(0, m.index))) continue;
    const head = t.slice(0, m.index + 1);
    if (head.length > SHORT_MAX) break;
    return { head, rest: t };
  }
  if (t.length <= SHORT_MAX) return { head: t, rest: null };
  const cut = t.slice(0, SHORT_MAX);
  return { head: `${cut.slice(0, cut.lastIndexOf(" "))} ...`, rest: t };
}

const pct = (x: number) => `${Math.round(x * 100)} %`;

export function stepView(item: TraceItem): StepView {
  const text = (item.output_summary ?? item.text ?? "").trim();
  const base = { detail: null, bars: null, final: false };

  if (item.type === "final") {
    // "Schwyz, Schwyz (Stufe B, Konfidenz 0.96)"
    const m = text.match(/^(.*?)\s*\(Stufe ([^,]+), Konfidenz ([\d.]+)\)\s*$/);
    if (m) {
      // "Schwyz, Schwyz" (locality, municipality) reads as one name; "?, ?" is nothing.
      const parts = m[1].split(",").map((x) => x.trim()).filter((x) => x && x !== "?");
      const place = [...new Set(parts)].join(", ");
      return { ...base, label: "Ergebnis", short: place ? `${place} · ${pct(Number(m[3]))}` : "nicht bestimmbar", final: true };
    }
    return { ...base, label: "Ergebnis", short: text, final: true };
  }

  const tool = item.tool ?? "";
  if (ATTEMPT[tool]) {
    // "Spital Schwyz, Schwyz: Der grosse Bau ..." -> the answer, the reasoning behind "mehr".
    const i = text.indexOf(": ");
    return { ...base, label: ATTEMPT[tool], short: i > 0 ? text.slice(0, i) : firstSentence(text).head, detail: i > 0 ? text.slice(i + 2) : null };
  }
  if (tool === "web_detection") {
    const terms = text.replace(/^Websuche:\s*/, "");
    if (!terms || /keine Websuche/i.test(text)) return { ...base, label: "Websuche", short: "kein Treffer" };
    const n = terms.split(",").length;
    return { ...base, label: "Websuche", short: `${n} Stichworte, kein Ortsname`, detail: terms };
  }
  if (tool === "check") {
    // "Spital Schwyz: 19 Punkte; Alterszentrum Acherhof: 58 Punkte"
    const bars = text
      .split(";")
      .map((part) => part.trim().match(/^(.*):\s*(\d+)\s*Punkte?$/))
      .filter((m): m is RegExpMatchArray => m !== null)
      .map((m) => ({ name: m[1].trim(), points: Number(m[2]) }))
      .sort((a, b) => b.points - a.points);
    if (bars.length) return { ...base, label: "Bildvergleich vor Ort", short: "", bars };
    return { ...base, label: "Bildvergleich vor Ort", short: text };
  }
  const label = tool === "judge" ? "Entscheid" : tool === "claude" ? "Einschätzung" : item.type === "thought" ? "Überlegung" : toolLabel(tool);
  const { head, rest } = firstSentence(text);
  return { ...base, label, short: head, detail: rest };
}
