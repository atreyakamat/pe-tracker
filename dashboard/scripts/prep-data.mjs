// Copies the tracker's data into public/data so the static site can fetch it.
// Real history wins. If none exists yet, falls back to SYNTHETIC demo data and flags it.
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = resolve(root, "dashboard", "public", "data");
mkdirSync(out, { recursive: true });

const real = resolve(root, "data", "nifty50_pe.json");
const demo = resolve(root, "data", "demo.json");
const state = resolve(root, "data", "state.json");

let meta;
if (existsSync(real)) {
  copyFileSync(real, resolve(out, "history.json"));
  meta = { demo: false, source: "niftyindices / NSE" };
  if (existsSync(state)) copyFileSync(state, resolve(out, "state.json"));
} else if (existsSync(demo)) {
  copyFileSync(demo, resolve(out, "history.json"));
  meta = { demo: true, source: "synthetic demo data" };
  console.warn("[prep-data] No real history found, using SYNTHETIC demo data.");
} else {
  writeFileSync(resolve(out, "history.json"), "[]");
  meta = { demo: false, source: "none", empty: true };
  console.warn("[prep-data] No data at all. Run `python -m tracker.run backfill` (or `demo`).");
}
writeFileSync(resolve(out, "meta.json"), JSON.stringify(meta));
