// Copies contracts/fixtures/ to public/fixtures/ for mock mode.
// The copies are generated: never edit them, edit contracts/fixtures/ on main instead.
import { cpSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = resolve(root, "../contracts/fixtures");
const dest = resolve(root, "public/fixtures");

rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log(`fixtures: ${src} -> ${dest}`);
