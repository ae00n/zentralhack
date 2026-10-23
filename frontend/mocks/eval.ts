// Mock-only additions to the eval_summary fixture: the keys Said's eval runner writes beyond the contract
// (metrics block, decade_n, n_eval, failure confidence). Invented numbers, consistent with the fixture.
import type { EvalSummary } from "@/lib/types";

function muni(n: number, accuracy: number, extra: Record<string, unknown> = {}) {
  return { n, accuracy, ...extra };
}

export function mockEvalExtras(base: EvalSummary): EvalSummary {
  return {
    ...base,
    decade_n: 200,
    decade_posted_at_or_before: 0.84,
    coord_n: 64,
    n_eval: 300,
    n_missing: 0,
    failures: base.failures.map((f) => ({ confidence: 0.78, subset: "card_exact", place_name_printed: false, ...f })),
    metrics: {
      n_truth: 300,
      n_scored: 300,
      all: {
        municipality: muni(300, 0.71, {
          accuracy_printed: 0.93,
          n_printed: 140,
          accuracy_not_printed: 0.52,
          n_not_printed: 160,
          "conf_0.7": { coverage: 0.55, accuracy: 0.85 },
          "conf_0.8": { coverage: 0.4, accuracy: 0.9 },
          "conf_0.9": { coverage: 0.2, accuracy: 0.96 },
        }),
      },
      card_exact: { municipality: muni(120, 0.78) },
      card_posted: { municipality: muni(100, 0.7) },
      photo_dated: { municipality: muni(80, 0.62) },
    },
  };
}
