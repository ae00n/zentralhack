// Mock-only challenge photos (CONTRACTS v3 section 2) and their results, for mock mode.
// Shaped like the real SG.CIV.17 set; every image is the public-domain fixture (public/fixtures/sample.jpg).
// Three states the UI must show (FRONTPAGE_PLAN 8): sure + confirmed, "Prüfung nötig" with a reference
// match, and a photo whose place could not be determined.
import type { AnalysisResult, Evidence, PhotoRecord } from "@/lib/types";

/** The contract fixture record, used as the archive reference card ("Das Archiv kennt diesen Ort"). */
export const MOCK_REFERENCE_ID = "epics:PK_020566";

interface ChallengeInput {
  n: number;
  date: string; // dd.mm.yyyy
  time: string; // hh:mm:ss
  model: string;
  session?: number[];
  priority?: number;
}

function challenge({ n, date, time, model, session = [], priority = 1 }: ChallengeInput): PhotoRecord {
  const sig = `SG.CIV.17.${n}`;
  const [d, m, y] = date.split(".");
  return {
    id: `challenge:${sig}`,
    source: "challenge",
    source_id: sig,
    source_url: null,
    signature: sig,
    collection: "SG.CIV.17",
    kind: "ground",
    title: null,
    date: { raw: date, year_from: Number(y), year_to: Number(y), approximate: false },
    places: [],
    municipality: null,
    location: null,
    camera: null,
    photographer: null,
    license: { code: "stasz-private", credit: `Staatsarchiv Schwyz, ${sig}`, url: null },
    image: null,
    parent_id: null,
    crop_bbox: null,
    split: "challenge",
    raw: {
      file_name: `${sig}.jpg`,
      priority,
      exif: {
        datetime: `${y}:${m}:${d} ${time}`,
        make: model.startsWith("NIKON") ? "NIKON CORPORATION" : "Canon",
        model,
        focal_mm: 17,
        focal_35mm: 25,
        lat: null,
        lon: null,
      },
      session: session.map((s) => `challenge:SG.CIV.17.${s}`),
      original_size: [3008, 1960],
    },
  };
}

export const MOCK_CHALLENGE: PhotoRecord[] = [
  challenge({ n: 3, date: "24.02.2005", time: "10:39:27", model: "NIKON D1X", session: [408] }),
  challenge({ n: 12, date: "11.06.2007", time: "14:02:51", model: "NIKON D1X" }),
  challenge({ n: 40, date: "03.09.2009", time: "09:15:04", model: "Canon EOS 20D", session: [41, 42, 43, 44] }),
];

function ev(kind: string, summary: string, extra: Partial<Evidence> = {}): Evidence {
  return { kind, summary, ref_id: null, url: null, score: null, supports: true, ...extra };
}

const EMPTY = { value: null, confidence: 0, evidence: [] };

type ResultInput = Pick<AnalysisResult, "fields" | "overall_confidence" | "needs_review" | "trace"> & Partial<AnalysisResult>;

function result(photoId: string, r: ResultInput): AnalysisResult {
  return {
    photo_id: photoId,
    run_id: "2026-10-23T21:14:02Z-mock",
    status: "done",
    model: "claude-opus-5-5",
    composite: null,
    rejected_hypotheses: [],
    usage: { input_tokens: 24100, output_tokens: 2300, cost_usd: 0.05, budget_hit: false },
    created_at: "2026-10-23T21:14:09Z",
    ...r,
  };
}

/** SG.CIV.17.3: the brief's worked example (CHALLENGE_BRIEF 3), sure and already confirmed. */
const acherhof = result("challenge:SG.CIV.17.3", {
  fields: {
    locality: {
      value: "Schwyz",
      confidence: 0.94,
      evidence: [
        ev("address_register", "Amtliches Adressverzeichnis: Grundstrasse 32, 6430 Schwyz"),
        ev("named_building", "Alterszentrum Acherhof liegt 40 m vom Standort, in Schwyz"),
        ev("visual_cue", "Grosser und Kleiner Mythen im Hintergrund, Blick von Südwesten"),
      ],
    },
    municipality: {
      value: "Schwyz",
      confidence: 0.94,
      evidence: [
        ev("address_register", "Grundstrasse 32 liegt in der politischen Gemeinde Schwyz"),
        ev("named_building", "Acherhof ist im Gebäudeverzeichnis der Gemeinde Schwyz", {
          url: "https://www.openstreetmap.org/way/123456789",
        }),
        ev("session_photo", "SG.CIV.17.408 aus derselben Serie zeigt den Eingang des Acherhofs", {
          ref_id: "challenge:SG.CIV.17.408",
        }),
      ],
    },
    buildings: {
      value: ["Alterszentrum Acherhof"],
      confidence: 0.9,
      evidence: [
        ev("named_building", "Benanntes Gebäude 'Alterszentrum Acherhof' (Alters-/Pflegeheim), 40 m entfernt"),
        ev("visual_cue", "Mehrgeschossiger Pflegeheimbau mit Balkonen und Vordach"),
      ],
    },
    landscape_features: {
      value: ["Mythen"],
      confidence: 0.88,
      evidence: [ev("terrain", "Gipfelsilhouette passt zu Grosser und Kleiner Mythen aus Richtung Schwyz")],
    },
    street: {
      value: "Grundstrasse 32",
      confidence: 0.9,
      evidence: [ev("address_register", "Nächste amtliche Adresse zum Gebäude: Grundstrasse 32")],
    },
    coordinates: {
      value: { lat: 47.0228, lon: 8.6489, radius_m: 60 },
      confidence: 0.9,
      evidence: [ev("named_building", "Koordinaten des Acherhofs aus dem Gebäudeverzeichnis")],
    },
  },
  overall_confidence: 0.94,
  confidence_explanation:
    "Gemeinde durch 3 unabhängige Quellen bestätigt (Gebäudeadressverzeichnis, benanntes Gebäude, Foto derselben Serie); Strasse aus dem amtlichen Adressverzeichnis.",
  needs_review: false,
  review: { status: "bestaetigt", fields: {}, note: null, reviewed_at: "2026-10-24T08:12:00Z" },
  trace: [
    { step: 1, type: "thought", text: "Moderner Pflegeheimbau, im Hintergrund Grosser und Kleiner Mythen. Vermutlich Schwyz.", ms: 0 },
    { step: 2, type: "tool_call", tool: "named_buildings", input: { name: "Acherhof" }, output_summary: "1 Treffer: Alterszentrum Acherhof, Schwyz", ms: 120 },
    { step: 3, type: "tool_call", tool: "address_lookup", input: { lat: 47.0228, lon: 8.6489 }, output_summary: "Grundstrasse 32, 6430 Schwyz, Gemeinde Schwyz", ms: 90 },
    { step: 4, type: "tool_call", tool: "terrain_check", input: { peaks: ["Grosser Mythen"] }, output_summary: "Silhouette passt aus Richtung Südwest", ms: 640 },
    { step: 5, type: "final", text: "Schwyz, Alterszentrum Acherhof, Grundstrasse 32. Modell-Sicherheit 94 %.", ms: 0 },
  ],
});

/** SG.CIV.17.12: below 0.9, with a verified archive reference (FRONTPAGE_PLAN 5, "Das Archiv kennt diesen Ort"). */
const brunnen = result("challenge:SG.CIV.17.12", {
  fields: {
    locality: {
      value: "Brunnen",
      confidence: 0.72,
      evidence: [
        ev("similar_image", "Referenzkarte zeigt dieselbe Uferpartie mit Blick auf den Urnersee", {
          ref_id: MOCK_REFERENCE_ID,
          score: 0.81,
          verified: true,
          inliers: 212,
        }),
        ev("visual_cue", "Seeufer mit Schiffsteg, Berge auf der Gegenseite"),
      ],
    },
    municipality: {
      value: "Ingenbohl",
      confidence: 0.72,
      evidence: [
        ev("address_register", "Brunnen gehört zur politischen Gemeinde Ingenbohl"),
        ev("visual_cue", "Seeufer könnte auch Sisikon sein", { supports: false }),
      ],
    },
    buildings: EMPTY,
    landscape_features: {
      value: ["Vierwaldstättersee", "Urirotstock"],
      confidence: 0.85,
      evidence: [ev("terrain", "Gipfel auf der Gegenseite passen zu Urirotstock und Gitschen")],
    },
    street: EMPTY,
    coordinates: {
      value: { lat: 46.984, lon: 8.6086, radius_m: 400 },
      confidence: 0.7,
      evidence: [ev("similar_image", "Standort der Referenzkarte")],
    },
  },
  overall_confidence: 0.72,
  confidence_explanation:
    "Ortschaft durch 2 unabhängige Quellen gestützt (verifiziertes Referenzfoto, Bildmerkmal); eine Quelle spricht für Sisikon; Gebäude und Strasse nicht bestimmbar.",
  needs_review: true,
  review: null,
  rejected_hypotheses: [{ field: "municipality", value: "Sisikon", reason: "Schiffsteg und Uferlinie passen zu Brunnen, nicht zu Sisikon" }],
  trace: [
    { step: 1, type: "thought", text: "Seeufer mit Schiffsteg, gegenüber hohe Gipfel. Urnersee?", ms: 0 },
    { step: 2, type: "tool_call", tool: "similar_images", input: { k: 8, verify: true }, output_summary: "1 verifizierter Treffer: Uferpartie bei Brunnen (212 Punkte)", ms: 820 },
    { step: 3, type: "tool_call", tool: "address_lookup", input: { lat: 46.984, lon: 8.6086 }, output_summary: "Ortschaft Brunnen, Gemeinde Ingenbohl, keine Adresse in 50 m", ms: 80 },
    { step: 4, type: "final", text: "Brunnen (Ingenbohl), Modell-Sicherheit 72 %. Prüfung nötig.", ms: 0 },
  ],
});

/** SG.CIV.17.40: nothing provable about the place, so the fields stay empty ("nicht bestimmbar"). */
const offen = result("challenge:SG.CIV.17.40", {
  fields: {
    locality: EMPTY,
    municipality: EMPTY,
    buildings: EMPTY,
    landscape_features: {
      value: ["Wald"],
      confidence: 0.4,
      evidence: [ev("visual_cue", "Mischwald am Hang, kein Gipfel und kein Gewässer sichtbar")],
    },
    street: EMPTY,
    coordinates: EMPTY,
  },
  overall_confidence: 0.2,
  confidence_explanation: "Keine unabhängige Quelle für Ortschaft oder Gemeinde gefunden; alle Ortsfelder nicht bestimmbar.",
  needs_review: true,
  review: null,
  trace: [
    { step: 1, type: "thought", text: "Waldweg ohne Gebäude, Schild unleserlich.", ms: 0 },
    { step: 2, type: "tool_call", tool: "similar_images", input: { k: 8, verify: true }, output_summary: "Kein verifizierter Treffer", ms: 790 },
    { step: 3, type: "final", text: "Ort nicht bestimmbar. Prüfung nötig.", ms: 0 },
  ],
});

export const MOCK_CHALLENGE_RESULTS: Record<string, AnalysisResult> = {
  [acherhof.photo_id]: acherhof,
  [brunnen.photo_id]: brunnen,
  [offen.photo_id]: offen,
};
