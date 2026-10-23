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
  /** status "error" only: German message for the UI (Said's jobs.py), plus a technical detail. */
  error?: string;
  error_detail?: string;
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

/** Municipality metrics from data_pipeline.metrics.score. */
export interface MuniMetrics {
  n: number;
  accuracy: number | null;
  accuracy_printed?: number | null;
  n_printed?: number;
  accuracy_not_printed?: number | null;
  n_not_printed?: number;
  /** keys "conf_0.7", "conf_0.8", "conf_0.9" */
  [conf: `conf_${string}`]: { coverage: number | null; accuracy: number | null } | undefined;
}

/** EvalSummary.metrics: "all" plus one entry per eval subset (card_exact, card_posted, photo_dated). */
export interface EvalMetrics {
  n_truth?: number;
  n_scored?: number;
  [subset: string]: { municipality: MuniMetrics; year?: Record<string, number | null> } | number | undefined;
}

/**
 * Optional keys beyond CONTRACTS section 7 are what Said's agent/eval/summary.py writes (said/agent 4fbd332).
 * _fixture_note marks the made-up fixture, which /eval/summary also serves before the first eval run.
 */
export interface EvalSummary {
  n: number;
  model: string;
  created_at: string;
  municipality_accuracy: number;
  decade_accuracy: number;
  decade_within_one: number;
  decade_n?: number;
  decade_posted_at_or_before?: number | null;
  median_coord_error_km: number | null;
  coord_n?: number;
  calibration: { bin: string; n: number; accuracy: number | null; mean_confidence?: number | null }[];
  by_municipality: { municipality: string; n: number; accuracy: number }[];
  baseline: { similarity_only_municipality_accuracy?: number; n?: number };
  failures: {
    photo_id: string;
    expected: string;
    got: string;
    why: string;
    confidence?: number;
    subset?: string;
    place_name_printed?: boolean;
  }[];
  cost_usd: number;
  n_eval?: number;
  n_missing?: number;
  metrics?: EvalMetrics;
  _fixture_note?: string;
}

/** Status "needs_review" and the needs_review flag both mean "Prüfung nötig" (OPEN_FRONTEND_QUESTIONS 3.5). */
export function needsReview(r: AnalysisResult): boolean {
  return r.needs_review || r.status === "needs_review";
}
