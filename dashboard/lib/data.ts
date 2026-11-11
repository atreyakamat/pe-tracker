import { outlierCap, type Row, type Zone } from "./stats";

export type IndexInfo = { key: string; label: string; group: string; core: boolean };
export type Meta = { demo: boolean; source: string; empty?: boolean };
export type Latest = Record<string, { zone: Zone; pe: number; percentile: number; composite: number | null }>;

export type TableRow = {
  key: string; label: string; group: string; pe: number; zone: Zone; pe_percentile: number;
  pb: number | null; pb_percentile: number | null; div_yield: number | null; dy_percentile: number | null;
  composite: number | null; median_pe: number;
  outlier_days: number; outlier_share: number;
};
export type Relative = { a: string; b: string; date: string; premium: number; median: number; percentile: number; min: number; max: number };
export type Compare = {
  date: string | null;
  table: TableRow[];
  relative: Relative[];
  correlation: { keys: string[]; matrix: (number | null)[][]; years: number };
  insights: string[];
};

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export const loadIndices = () => getJson<IndexInfo[]>("/data/indices.json");
export const loadMeta = () => getJson<Meta>("/data/meta.json");
export const loadLatest = () => getJson<Latest>("/data/latest.json").catch(() => ({}) as Latest);
export const loadCompare = () => getJson<Compare>("/data/compare.json");
export const loadHistory = (key: string) => getJson<Row[]>(`/data/${key}.json`);

/** Premium (%) of A's PE over B's PE on dates both have, skipping days either index is an outlier. Mirrors tracker/compare.py. */
export function relativeSeries(a: Row[], b: Row[]): { date: string; premium: number }[] {
  const capA = outlierCap(a), capB = outlierCap(b);
  const bBy = new Map(b.map((r) => [r.date, r.pe]));
  const out: { date: string; premium: number }[] = [];
  for (const r of a) {
    const d = bBy.get(r.date);
    if (d && r.pe <= capA && d <= capB) out.push({ date: r.date, premium: (r.pe / d - 1) * 100 });
  }
  return out;
}
