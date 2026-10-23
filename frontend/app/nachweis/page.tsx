"use client";

// Nachweis (build step 7): the proof page. Numbers come from /eval/summary only.
// Calibration chart comes in step 10; until then calibration is a table.
import Link from "next/link";
import { useEffect, useState } from "react";
import Share from "@/components/nachweis/Share";
import { MODE, errorText, getEvalSummary, imageUrl } from "@/lib/api";
import { analyseHref, formatDate, formatPct } from "@/lib/format";
import { subsetLabel } from "@/lib/labels";
import type { EvalSummary, MuniMetrics } from "@/lib/types";

const CONF_LEVELS = ["0.7", "0.8", "0.9"];

function Big({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <p className="text-meta text-ink-muted">{label}</p>
      <p className="mt-1 font-serif text-[56px] leading-none">{value}</p>
      {note && <p className="mt-2 text-meta text-ink-muted">{note}</p>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-rule pt-4">
      <h2 className="font-serif text-section">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** One table row: label, muted n, share bar. */
function Row({ label, n, value }: { label: string; n?: number; value: number | null | undefined }) {
  return (
    <tr className="border-b border-rule last:border-b-0">
      <td className="py-2 pr-4">{label}</td>
      <td className="py-2 pr-4 text-right font-mono text-meta text-ink-muted">{n ?? ""}</td>
      <td className="py-2 text-right">
        <Share value={value} />
      </td>
    </tr>
  );
}

function Table({ head, children }: { head: string; children: React.ReactNode }) {
  return (
    <table className="w-full text-body">
      <thead>
        <tr className="border-b border-rule text-left text-meta text-ink-muted">
          <th className="pb-1.5 font-normal">{head}</th>
          <th className="w-16 pb-1.5 pr-4 text-right font-normal">n</th>
          <th className="w-[176px] pb-1.5 text-right font-normal">richtig</th>
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

function muniOf(s: EvalSummary, key: string): MuniMetrics | undefined {
  const entry = s.metrics?.[key];
  return typeof entry === "object" && entry ? entry.municipality : undefined;
}

export default function NachweisPage() {
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvalSummary()
      .then(setSummary)
      .catch((e: unknown) => setError(errorText(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-[1100px] px-4 py-8 md:px-8">
      <div className="border-b border-rule pb-4">
        <h1 className="font-serif text-page">Nachweis</h1>
        <p className="mt-1 text-meta text-ink-muted">
          Wie oft der Agent richtig liegt, gemessen an Fotos, deren Ort und Datum das Archiv kennt.
        </p>
      </div>

      {error && <p className="mt-6 text-bad">Auswertung konnte nicht geladen werden: {error}</p>}
      {!error && loading && <p className="mt-6 text-ink-muted">Lade Auswertung ...</p>}
      {!error && !loading && !summary && (
        <p className="mt-6 text-ink-muted">Noch keine Auswertung. Die Zahlen erscheinen nach dem Eval-Lauf.</p>
      )}
      {summary && <Report s={summary} />}
    </main>
  );
}

function Report({ s }: { s: EvalSummary }) {
  const all = muniOf(s, "all");
  const subsets = Object.keys(s.metrics ?? {}).filter((k) => k !== "all" && muniOf(s, k));
  const base = s.baseline?.similarity_only_municipality_accuracy;
  const failure = s.failures[0];

  return (
    <div className="fade-in">
      <p className="mt-3 font-mono text-meta text-ink-muted">
        {[
          `${s.n}${s.n_eval && s.n_eval !== s.n ? ` von ${s.n_eval}` : ""} Fotos ausgewertet`,
          s.model,
          formatDate(s.created_at),
          `Kosten $${s.cost_usd.toFixed(2)}`,
        ].join(" · ")}
      </p>
      {MODE === "mock" && (
        <p className="mt-1 text-meta text-warn">Beispieldaten: erfundene Zahlen, nicht für den Pitch.</p>
      )}

      <div className="mt-8 grid grid-cols-2 gap-x-8 gap-y-8 md:grid-cols-4">
        <Big
          label="Gemeinde richtig"
          value={formatPct(s.municipality_accuracy)}
          note={base !== undefined ? `Nur Bildähnlichkeit: ${formatPct(base)}` : undefined}
        />
        <Big
          label="Jahrzehnt richtig"
          value={formatPct(s.decade_accuracy)}
          note={s.decade_n ? `${s.decade_n} Fotos mit genauem Jahr` : undefined}
        />
        <Big label="Jahrzehnt ±1" value={formatPct(s.decade_within_one)} note="höchstens ein Jahrzehnt daneben" />
        <Big
          label="Fotos ausgewertet"
          value={String(s.n)}
          note={
            s.median_coord_error_km !== null
              ? `Koordinaten: Median-Fehler ${s.median_coord_error_km.toLocaleString("de-CH")} km`
              : undefined
          }
        />
      </div>

      <div className="mt-12 grid gap-x-12 gap-y-10 lg:grid-cols-2">
        {base !== undefined && (
          <Section title="Agent gegen reine Bildähnlichkeit">
            <Table head="Gemeinde">
              <Row label="Agent (Evidenz, Karte, Text)" value={s.municipality_accuracy} />
              <Row label="Nur ähnlichste Archivbilder" n={s.baseline.n} value={base} />
            </Table>
            <p className="mt-2 text-meta text-ink-muted">
              {`${Math.round((s.municipality_accuracy - base) * 100)} Prozentpunkte besser als das nächste ähnliche Bild.`}
            </p>
          </Section>
        )}

        {all && (
          <Section title="Wann die Gemeinde stimmt">
            <Table head="Fotos">
              {all.accuracy_printed !== undefined && (
                <Row label="Ortsname auf der Karte gedruckt" n={all.n_printed} value={all.accuracy_printed} />
              )}
              {all.accuracy_not_printed !== undefined && (
                <Row label="Kein Ortsname gedruckt" n={all.n_not_printed} value={all.accuracy_not_printed} />
              )}
              {subsets.map((k) => {
                const m = muniOf(s, k)!;
                return <Row key={k} label={subsetLabel(k)} n={m.n} value={m.accuracy} />;
              })}
            </Table>
          </Section>
        )}

        <Section title="Konfidenz">
          {all && (
            <ul className="mb-4 space-y-1.5">
              {CONF_LEVELS.map((c) => {
                const lvl = all[`conf_${c}`];
                if (!lvl || lvl.coverage === null) return null;
                return (
                  <li key={c}>
                    Ab <span className="font-mono">{c}</span>: {formatPct(lvl.coverage)} der Fotos, davon{" "}
                    <span className="font-medium">{formatPct(lvl.accuracy)}</span> richtig
                  </li>
                );
              })}
            </ul>
          )}
          <Table head="Konfidenz Gemeinde">
            {s.calibration.map((c) => (
              <Row key={c.bin} label={c.bin.replace("-", " bis ")} n={c.n} value={c.accuracy} />
            ))}
          </Table>
        </Section>

        {s.by_municipality.length > 0 && (
          <Section title="Nach Gemeinde">
            <Table head="Gemeinde">
              {s.by_municipality.map((m) => (
                <Row key={m.municipality} label={m.municipality} n={m.n} value={m.accuracy} />
              ))}
            </Table>
          </Section>
        )}
      </div>

      {failure && (
        <div className="mt-12">
          <Section title="Ein ehrlicher Fehlerfall">
            <div className="grid gap-6 sm:grid-cols-[240px_1fr]">
              <div className="flex aspect-[3/2] items-center justify-center bg-paper-2 p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={imageUrl(failure.photo_id, 480)} alt="" className="max-h-full max-w-full object-contain" />
              </div>
              <div>
                <p>
                  Richtig ist <span className="font-medium">{failure.expected}</span>, der Agent sagte{" "}
                  <span className="font-medium text-bad">{failure.got}</span>
                  {failure.confidence !== undefined && (
                    <span className="text-ink-muted">
                      {" "}
                      mit Konfidenz <span className="font-mono">{failure.confidence.toFixed(2)}</span>
                    </span>
                  )}
                  .
                </p>
                <p className="mt-2 text-ink-muted">{failure.why}</p>
                <p className="mt-3 text-meta text-ink-muted">
                  <span className="font-mono">{failure.photo_id}</span>
                  {" · "}
                  <Link href={analyseHref(failure.photo_id)} className="hover:text-accent">
                    Analyse ansehen
                  </Link>
                  {s.failures.length > 1 && ` · ${s.failures.length - 1} weitere Fehler in der Auswertung`}
                </p>
              </div>
            </div>
          </Section>
        </div>
      )}
    </div>
  );
}
