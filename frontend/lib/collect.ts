// Collects the images of a drop or file pick (UPLOAD_PLAN step 1): loose images, whole folders and ZIPs,
// unpacked in the browser. Each image keeps its path (inside the ZIP or the dropped folder) as file_name,
// the Excel key. Everything else is listed as skipped with a German reason, never dropped silently,
// except system junk (__MACOSX, ._*, .DS_Store, Thumbs.db).
import { unzip } from "fflate";

export interface PickedFile {
  /** Path inside the ZIP or folder, "/" separated. */
  file_name: string;
  file: Blob;
  size: number;
}

export interface SkippedFile {
  file_name: string;
  reason: string;
}

export interface Collected {
  images: PickedFile[];
  skipped: SkippedFile[];
}

// What the backend reads with PIL (catalogue.save_upload); HEIC needs a plugin it does not have.
const IMAGE_TYPES: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  tif: "image/tiff",
  tiff: "image/tiff",
  webp: "image/webp",
};
// A ZIP is read into memory whole; browsers fail on buffers of about 2 GB.
const MAX_ZIP_BYTES = 1.5 * 1024 ** 3;

function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

function baseOf(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

function isJunk(path: string): boolean {
  const base = baseOf(path);
  return path.split("/").includes("__MACOSX") || base.startsWith("._") || base === ".DS_Store" || base === "Thumbs.db";
}

function isZip(name: string, type: string): boolean {
  return extOf(name) === "zip" || type === "application/zip" || type === "application/x-zip-compressed";
}

function reasonFor(name: string): string {
  const ext = extOf(name);
  if (ext === "heic" || ext === "heif") return "HEIC wird nicht unterstützt, bitte als JPEG exportieren";
  if (ext === "zip") return "ZIP in einer ZIP-Datei wird nicht entpackt";
  return "kein unterstütztes Bildformat";
}

function unzipAsync(data: Uint8Array): Promise<Record<string, Uint8Array>> {
  return new Promise((resolve, reject) => unzip(data, (err, files) => (err ? reject(err) : resolve(files))));
}

async function fromZip(zip: Blob, zipName: string, out: Collected): Promise<void> {
  if (zip.size > MAX_ZIP_BYTES) {
    out.skipped.push({ file_name: zipName, reason: "ZIP zu gross (über 1.5 GB), bitte aufteilen oder den Ordner ziehen" });
    return;
  }
  let entries: Record<string, Uint8Array>;
  try {
    entries = await unzipAsync(new Uint8Array(await zip.arrayBuffer()));
  } catch {
    out.skipped.push({ file_name: zipName, reason: "ZIP-Datei ist beschädigt oder verschlüsselt" });
    return;
  }
  for (const [path, data] of Object.entries(entries)) {
    if (path.endsWith("/") || isJunk(path)) continue; // folder entries and system files
    const type = IMAGE_TYPES[extOf(path)];
    if (!type) out.skipped.push({ file_name: path, reason: reasonFor(path) });
    else out.images.push({ file_name: path, file: new Blob([data as BlobPart], { type }), size: data.length });
  }
}

/** Loose files from an <input type="file"> (with webkitdirectory: webkitRelativePath is the path). */
export async function collectImages(files: Iterable<File>): Promise<Collected> {
  const out: Collected = { images: [], skipped: [] };
  for (const f of files) {
    const path = f.webkitRelativePath || f.name;
    if (isJunk(path)) continue;
    if (isZip(f.name, f.type)) await fromZip(f, path, out);
    else if (IMAGE_TYPES[extOf(f.name)]) out.images.push({ file_name: path, file: f, size: f.size });
    else out.skipped.push({ file_name: path, reason: reasonFor(f.name) });
  }
  // The same path twice (two drops, two ZIPs with the same layout): the Excel key must stay unique.
  const seen = new Set<string>();
  out.images = out.images.filter((p) => {
    if (!seen.has(p.file_name)) {
      seen.add(p.file_name);
      return true;
    }
    out.skipped.push({ file_name: p.file_name, reason: "doppelt, nur die erste Datei wird verwendet" });
    return false;
  });
  out.images.sort((a, b) => a.file_name.localeCompare(b.file_name, "de-CH", { numeric: true }));
  return out;
}

// --- drag and drop of folders (DataTransferItem.webkitGetAsEntry) ---

function fileOf(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

/** readEntries returns at most 100 entries per call; read until it returns none. */
async function readAll(dir: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
  const reader = dir.createReader();
  const all: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) return all;
    all.push(...batch);
  }
}

async function walk(entry: FileSystemEntry, prefix: string, out: File[]): Promise<void> {
  const path = prefix ? `${prefix}/${entry.name}` : entry.name;
  if (entry.isFile) {
    const f = await fileOf(entry as FileSystemFileEntry);
    // Carry the folder path the way webkitdirectory does, so collectImages treats both alike.
    Object.defineProperty(f, "webkitRelativePath", { value: path });
    out.push(f);
  } else if (entry.isDirectory) {
    for (const child of await readAll(entry as FileSystemDirectoryEntry)) await walk(child, path, out);
  }
}

/** Files of a drop, folders included (recursively). Falls back to dataTransfer.files without entry support. */
export async function filesFromDrop(dt: DataTransfer): Promise<File[]> {
  const entries = Array.from(dt.items)
    .filter((i) => i.kind === "file")
    .map((i) => i.webkitGetAsEntry?.() ?? null);
  if (!entries.length || entries.some((e) => e === null)) return Array.from(dt.files);
  const out: File[] = [];
  for (const e of entries) await walk(e as FileSystemEntry, "", out);
  return out;
}
