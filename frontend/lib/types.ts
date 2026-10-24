// Hand-written from contracts/schemas/*.schema.json and docs/CONTRACTS.md.
// Unknown keys from the backend are ignored (CONTRACTS conventions), so keep these types to what the UI reads.

export type Source = "staatsarchiv" | "smapshot" | "epics" | "lubis" | "nb" | "upload" | "challenge";

/** record.raw of a challenge photo (CONTRACTS v3 section 2). Other sources keep their own raw keys. */
export interface ChallengeRaw {
  file_name?: string; // the Excel key (Dateiname)
  priority?: number; // 1 = Prio-1 set of 50, 2 = the rest
  exif?: {
    datetime: string | null;
    make: string | null;
    model: string | null;
    focal_mm?: number | null;
    focal_35mm?: number | null;
    lat: number | null;
    lon: number | null;
  };
  session?: string[]; // sibling ids: same camera, under 30 min apart
  original_size?: [number, number];
}

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
  split: "eval" | "showcase" | "reference" | "challenge" | "none";
  raw?: ChallengeRaw & Record<string, unknown>;
}

export type EvidenceKind =
  | "visual_cue"
  | "text_on_card"
  | "similar_image"
  | "archive_record"
  | "swisstopo_place"
  | "terrain"
  | "map_layer"
  // v3
  | "address_register"
  | "named_building"
  | "exif"
  | "session_photo";

export interface Evidence {
  // string: date_hints may add kinds outside the enum (OPEN_FRONTEND_QUESTIONS 3.7)
  kind: EvidenceKind | string;
  summary: string;
  ref_id?: string | null;
  url?: string | null;
  score?: number | null;
  supports: boolean;
  /** similar_image only, asked from Said (FRONTPAGE_PLAN 9): LightGlue-verified match and its inlier count. */
  verified?: boolean;
  inliers?: number;
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

/** v3 order = the archive's priority. A field that cannot be determined has value null (or []) and confidence 0. */
export interface ResultFields {
  locality: Field<string>; // Ortschaft
  municipality: Field<string>; // Gemeinde
  buildings: Field<string[]>;
  landscape_features: Field<string[]>; // See/Fluss/Berg
  street: Field<string>; // street + number when known
  coordinates: Field<Coordinates>;
  // Optional in v3: challenge photos carry the EXIF date in the record; postcard results still have them.
  place?: Field<string>;
  decade?: Field<number>;
  year_range?: Field<{ from: number; to: number }>;
}

export type FieldKey = keyof ResultFields;

/** The five fields the archivist reviews, in the brief's order. */
export type ReviewField = "locality" | "municipality" | "buildings" | "landscape_features" | "street";

export type ReviewStatus = "offen" | "bestaetigt" | "korrigiert";

export interface Review {
  status: ReviewStatus;
  /** Only the corrected fields. */
  fields: Partial<Record<ReviewField, string | string[] | null>>;
  note: string | null;
  reviewed_at: string | null;
}

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
  /** v3: German sentence on how overall_confidence came about. */
  confidence_explanation?: string | null;
  /** v3: set by POST /review. */
  review?: Review | null;
  /** status "error" only: German message for the UI (Said's jobs.py), plus a technical detail. */
  error?: string;
  error_detail?: string;
  /**
   * Where the result's landmarks are in the photo (Said, 24.10., for the backend: one vision pass per
   * photo). x and y are 0..1 of the image width and height, y null when only the direction is known.
   */
  photo_marks?: PhotoMark[] | null;
}

export interface PhotoMark {
  name: string;
  kind: "mountain" | "water" | "building" | "place";
  x: number;
  y: number | null;
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

/**
 * Batch upload (frontend/context/UPLOAD_PLAN.md). Proposed shape for /batches, not in the contract yet;
 * the client runner keeps the same shape in localStorage.
 */
export type BatchItemStatus = "queued" | "uploading" | "running" | "done" | "error" | "skipped";

export interface BatchItem {
  /** Path inside the ZIP or folder, e.g. "Brunnen/IMG_0012.jpg": the Excel key (Dateiname). */
  file_name: string;
  size: number;
  /** upload:<sha1>, or challenge:<signature> for a known challenge photo, once the image is stored. */
  photo_id: string | null;
  job_id: string | null;
  status: BatchItemStatus;
  /** German, for status "error" and "skipped". */
  error: string | null;
}

export interface Batch {
  id: string;
  name: string;
  created_at: string;
  /** "server": the backend runs the queue (/batches); "client": this browser does, over POST /analyze. */
  runner: "server" | "client";
  items: BatchItem[];
  cost_usd?: number | null;
}

/** Status "needs_review" and the needs_review flag both mean "Prüfung nötig" (OPEN_FRONTEND_QUESTIONS 3.5). */
export function needsReview(r: AnalysisResult): boolean {
  return r.needs_review || r.status === "needs_review";
}

/**
 * Hand-checked sample of challenge results (CHALLENGE_BRIEF 4, challenge_qc.jsonl). Proposed shape for
 * GET /qc/summary, to agree with Said and Dijar (OPEN_FRONTEND_QUESTIONS 5); not in the contract yet.
 */
export interface QcSummary {
  n: number;
  /** Gemeinde correct in the sample. */
  municipality_correct: number;
  /** Bins by overall_confidence: "<0.5", "0.5-0.9", ">=0.9". */
  bins: { bin: string; n: number; correct: number }[];
  cost_usd_per_photo?: number | null;
  created_at?: string;
}
