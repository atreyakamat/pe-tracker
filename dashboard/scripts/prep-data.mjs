// Copies the tracker's output into public/data so the static site can fetch it.
// Real data wins. If none exists yet, falls back to SYNTHETIC demo data in data/demo/ and flags it.
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = resolve(root, "dashboard", "public", "data");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const realDir = resolve(root, "data");
const demoDir = resolve(root, "data", "demo");
const hasManifest = (dir) => existsSync(resolve(dir, "indices.json")) && existsSync(resolve(dir, "compare.json"));

let src = null, meta;
if (hasManifest(realDir)) {
  src = realDir;
  meta = { demo: false, source: "niftyindices / NSE" };
} else if (hasManifest(demoDir)) {
  src = demoDir;
  meta = { demo: true, source: "synthetic demo data" };
  console.warn("[prep-data] No real data found, using SYNTHETIC demo data.");
} else {
  writeFileSync(resolve(out, "indices.json"), "[]");
  meta = { demo: false, source: "none", empty: true };
  console.warn("[prep-data] No data at all. Run `python -m tracker.run backfill` then `daily` (or `demo`).");
}

if (src) {
  const keys = JSON.parse(readFileSync(resolve(src, "indices.json"), "utf8")).map((i) => i.key);
  for (const f of ["indices.json", "compare.json", "latest.json", ...keys.map((k) => `${k}.json`)]) {
    if (existsSync(resolve(src, f))) copyFileSync(resolve(src, f), resolve(out, f));
    else console.warn(`[prep-data] missing ${f}`);
  }
}
writeFileSync(resolve(out, "meta.json"), JSON.stringify(meta));
console.log(`[prep-data] ${src ?? "no source"} -> public/data (${readdirSync(out).length} files)`);
