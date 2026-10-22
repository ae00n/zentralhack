// Mock-only result variants, derived from the contract fixture, to exercise UI states the fixture lacks.
import type { AnalysisResult } from "@/lib/types";

/** Low confidence on the core fields: amber rows and "Prüfung nötig". */
function needsReviewVariant(base: AnalysisResult): AnalysisResult {
  const f = base.fields;
  return {
    ...base,
    status: "done",
    needs_review: true,
    overall_confidence: 0.41,
    trace: base.trace.map((t) =>
      t.type === "final" ? { ...t, text: "Ingenbohl oder Sisikon, Jahrzehnt unsicher, Konfidenz 0.41. Prüfung nötig." } : t,
    ),
    fields: {
      ...f,
      municipality: {
        value: "Ingenbohl",
        confidence: 0.44,
        evidence: [
          ...f.municipality.evidence.slice(0, 1),
          {
            kind: "similar_image",
            summary: "Nur 3 von 8 ähnlichen Bildern liegen in Ingenbohl, 3 in Sisikon",
            score: 0.62,
            supports: false,
          },
        ],
      },
      decade: {
        value: 1910,
        confidence: 0.32,
        evidence: [
          { kind: "visual_cue", summary: "Lichtdruck ohne Kolorierung, möglich von 1900 bis 1930", supports: true },
          { kind: "year_probe", summary: "Bildstil-Modell: wahrscheinlich 1895 bis 1940", supports: true },
        ],
      },
      year_range: { value: { from: 1900, to: 1930 }, confidence: 0.3, evidence: [] },
      place: { value: null, confidence: 0.2, evidence: [] },
    },
  };
}

/** Per mock photo id: how to change the fixture result. Ids not listed get the fixture as is. */
export const MOCK_RESULT_VARIANTS: Record<string, (base: AnalysisResult) => AnalysisResult> = {
  "stasz:mock-02": needsReviewVariant,
};
