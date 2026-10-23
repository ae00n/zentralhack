// German UI labels for contract keys. Unknown keys fall back to the raw key.
import type { FieldKey } from "./types";

/**
 * Result rows in display order: the brief's five fields first (CONTRACTS v3), then the optional
 * postcard fields, shown only when a result has them. year_range is shown inside the Jahrzehnt row.
 */
export const FIELD_ROWS: { key: FieldKey; label: string }[] = [
  { key: "locality", label: "Ortschaft" },
  { key: "municipality", label: "Gemeinde" },
  { key: "buildings", label: "Gebäude" },
  { key: "landscape_features", label: "See/Fluss/Berg" },
  { key: "street", label: "Strasse" },
  { key: "place", label: "Ort" },
  { key: "decade", label: "Jahrzehnt" },
  { key: "coordinates", label: "Koordinaten" },
];

export const FIELD_LABELS: Record<string, string> = {
  ...Object.fromEntries(FIELD_ROWS.map((r) => [r.key, r.label])),
  year_range: "Zeitraum",
};

const EVIDENCE_LABELS: Record<string, string> = {
  visual_cue: "Bildmerkmal",
  text_on_card: "Aufdruck",
  similar_image: "Ähnliches Bild",
  archive_record: "Archivdatensatz",
  swisstopo_place: "swisstopo Ortsname",
  terrain: "Gelände",
  map_layer: "Historische Karte",
  // date_hints kinds (question 3.7)
  near_duplicate: "Fast gleiche Karte",
  card_number: "Kartennummer",
  nb_negative: "Negativ Nationalbibliothek",
  publisher_rule: "Verlag",
  year_probe: "Bildstil",
};

const TOOL_LABELS: Record<string, string> = {
  similar_images: "Ähnliche Bilder",
  date_hints: "Datierungshinweise",
  archive_lookup: "Archivsuche",
  swisstopo_search: "swisstopo Suche",
  swisstopo_height: "Höhenabfrage",
  swisstopo_profile: "Höhenprofil",
  terrain_check: "Geländeprüfung",
  submit_result: "Ergebnis",
};

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

export function evidenceLabel(kind: string): string {
  return EVIDENCE_LABELS[kind] ?? kind;
}

export function toolLabel(tool: string | undefined): string {
  if (!tool) return "Werkzeug";
  return TOOL_LABELS[tool] ?? tool;
}

/** Eval subsets (CONTRACTS section 2). */
export const SUBSET_LABELS: Record<string, string> = {
  card_exact: "Ansichtskarten, nicht gelaufen",
  card_posted: "Ansichtskarten, gelaufen",
  photo_dated: "Fotos mit Aufnahmedatum",
};

export function subsetLabel(key: string): string {
  return SUBSET_LABELS[key] ?? key;
}
