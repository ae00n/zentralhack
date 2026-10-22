// Hand-written from contracts/schemas/*.schema.json and docs/CONTRACTS.md.
// Unknown keys from the backend are ignored (CONTRACTS conventions), so keep these types to what the UI reads.

export type Source = "staatsarchiv" | "smapshot" | "epics" | "lubis" | "nb" | "upload";

export interface PhotoRecord {
  id: string;
  source: Source;
  source_id: string;
  source_url: string | null;
  signature: string | null;
  collection: string | null;
  kind: "postcard" | "aerial" | "ground" | "unknown";
  title: string | null;
  date: {
    raw: string | null;
    year_from: number | null;
    year_to: number | null;
    approximate: boolean;
  } | null;
  places: string[];
  municipality: string | null;
  location: {
    lat: number;
    lon: number;
    method: string;
    precision_m: number | null;
  } | null;
  camera: {
    lat: number;
    lon: number;
    altitude_m: number | null;
    azimuth: number | null;
    tilt: number | null;
    roll: number | null;
    focal: number | null;
  } | null;
  photographer: string | null;
  license: { code: string; credit: string; url: string | null } | null;
  image: { path: string; width: number; height: number; sha1: string } | null;
  parent_id: string | null;
  crop_bbox: number[] | null;
  split: "eval" | "showcase" | "reference" | "none";
}

export type EvidenceKind =
  | "visual_cue"
  | "text_on_card"
  | "similar_image"
  | "archive_record"
  | "swisstopo_place"
  | "terrain"
  | "map_layer";

export interface Evidence {
  // string: date_hints may add kinds outside the enum (OPEN_FRONTEND_QUESTIONS 3.7)
  kind: EvidenceKind | string;
  summary: string;
  ref_id?: string | null;
  url?: string | null;
  score?: number | null;
  supports: boolean;
}

export interface Field<T> {
  value: T | null;
  confidence: number;
  evidence: Evidence[];
}

export interface Coordinates {
  lat: number;
  lon: number;
  radius_m: number;
}

export interface ResultFields {
  municipality: Field<string>;
  place: Field<string>;
  buildings: Field<string[]>;
  landscape_features: Field<string[]>;
  decade: Field<number>;
  year_range: Field<{ from: number; to: number }>;
  coordinates: Field<Coordinates>;
}

export type FieldKey = keyof ResultFields;

export interface TraceItem {
  step: number;
  type: "thought" | "tool_call" | "final" | string;
  text?: string;
  tool?: string;
  input?: Record<string, unknown>;
  output_summary?: string;
  ms: number;
}

export interface AnalysisResult {
  photo_id: string;
  run_id: string;
  status: "queued" | "running" | "done" | "needs_review" | "error";
  model: string;
  composite: { is_composite: boolean; parts: string[] } | null;
  fields: ResultFields;
  overall_confidence: number;
  needs_review: boolean;
  rejected_hypotheses: { field: FieldKey | string; value: unknown; reason: string }[];
  trace: TraceItem[];
  usage: { input_tokens: number; output_tokens: number; cost_usd: number; budget_hit: boolean } | null;
  created_at: string;
}

export interface Health {
  ok: boolean;
  model: string;
  offline: boolean;
  tiles_url: string;
}

export interface PhotoList {
  items: PhotoRecord[];
  total: number;
}

export interface TimelinePhoto {
  id: string;
  year_from: number | null;
  year_to: number | null;
  distance_m: number;
  image_url: string;
}

export interface Timeline {
  photos: TimelinePhoto[];
  map_years: number[];
}

export interface DemoItem {
  id: string;
  why: string;
  record: PhotoRecord;
}

export interface EvalSummary {
  n: number;
  model: string;
  created_at: string;
  municipality_accuracy: number;
  decade_accuracy: number;
  decade_within_one: number;
  median_coord_error_km: number;
  calibration: { bin: string; n: number; accuracy: number }[];
  by_municipality: { municipality: string; n: number; accuracy: number }[];
  baseline: { similarity_only_municipality_accuracy: number };
  failures: { photo_id: string; expected: string; got: string; why: string }[];
  cost_usd: number;
  metrics?: Record<string, unknown>;
}

/** Status "needs_review" and the needs_review flag both mean "Prüfung nötig" (OPEN_FRONTEND_QUESTIONS 3.5). */
export function needsReview(r: AnalysisResult): boolean {
  return r.needs_review || r.status === "needs_review";
}
