// Frontend-only mock records for mock mode (never shown in demo or live mode).
// Titles and signatures are invented placeholders shaped like Staatsarchiv records; every image is the
// public-domain fixture (public/fixtures/sample.jpg). Real records come from GET /photos.
import type { PhotoRecord } from "@/lib/types";

type MockInput = Pick<PhotoRecord, "id" | "title" | "kind"> & {
  signature: string;
  dateRaw?: string;
  year?: number;
  places?: string[];
};

function mock({ id, title, kind, signature, dateRaw, year, places = [] }: MockInput): PhotoRecord {
  const sourceId = id.split(":")[1];
  return {
    id,
    source: "staatsarchiv",
    source_id: sourceId,
    source_url: null,
    signature,
    collection: "SG.CIV.12",
    kind,
    title,
    date: dateRaw
      ? { raw: dateRaw, year_from: year ?? null, year_to: year ?? null, approximate: dateRaw.startsWith("ca.") }
      : { raw: "keine Angabe", year_from: null, year_to: null, approximate: false },
    places,
    municipality: null,
    location: null,
    camera: null,
    photographer: null,
    license: { code: "mock", credit: "Beispieldaten (Fixture-Bild: ETH-Bibliothek Zürich, Public Domain Mark)", url: null },
    image: { path: "sample.jpg", width: 1024, height: 671, sha1: "" },
    parent_id: null,
    crop_bbox: null,
    split: "showcase",
  };
}

export const MOCK_PHOTOS: PhotoRecord[] = [
  mock({ id: "stasz:mock-01", signature: "SG.CIV.12.M001", kind: "postcard", title: "Gruss aus dem Muotathal" }),
  mock({ id: "stasz:mock-02", signature: "SG.CIV.12.M002", kind: "postcard", title: "Partie am See" }),
  mock({ id: "stasz:mock-03", signature: "SG.CIV.12.M003", kind: "postcard", title: "Dorfstrasse mit Kirche" }),
  mock({ id: "stasz:mock-04", signature: "SG.CIV.12.M004", kind: "postcard", title: "Blick auf die Mythen" }),
  mock({ id: "stasz:mock-05", signature: "SG.CIV.12.M005", kind: "postcard", title: "Gasthaus zum Rössli" }),
  mock({ id: "stasz:mock-06", signature: "SG.CIV.04.M006", kind: "aerial", title: "Flugaufnahme Seeufer" }),
  mock({ id: "stasz:mock-07", signature: "SG.CIV.12.M007", kind: "postcard", title: "Kapelle am Wegrand" }),
  mock({ id: "stasz:mock-08", signature: "SG.CIV.12.M008", kind: "postcard", title: "Hauptplatz", dateRaw: "ca. 1915", year: 1915 }),
  mock({ id: "stasz:mock-09", signature: "SG.CIV.12.M009", kind: "postcard", title: "Kloster, Gesamtansicht", dateRaw: "1904", year: 1904 }),
  mock({ id: "stasz:mock-10", signature: "SG.CIV.12.M010", kind: "postcard", title: "Bahnhof mit Hotel", dateRaw: "vor 1930", year: 1930 }),
];

/** Pitch-order demo list for mock mode: the first three mock cards. */
export const MOCK_DEMO_IDS = ["stasz:mock-01", "stasz:mock-02", "stasz:mock-04"];
