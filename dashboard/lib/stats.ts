// Mirrors tracker/signal.py so chart bands match the Telegram alerts.
export type Row = { date: string; pe: number; pb: number | null; div_yield: number | null };
export type Zone = "BUY" | "NEUTRAL" | "EXPENSIVE";

export const BUY_PCT = 25;
export const EXPENSIVE_PCT = 75;
export const LOOKBACK_YEARS = 10;
/** Days with PE above this multiple of the window median are earnings-collapse artifacts (mirrors OUTLIER_MULT in Python). */
export const OUTLIER_MULT = 3;

export function medianOf(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** PE cap for a window: OUTLIER_MULT x median. Outliers barely move the median, so it is a stable yardstick. */
export function outlierCap(rows: { pe: number }[]): number {
  return rows.length ? OUTLIER_MULT * medianOf(rows.map((r) => r.pe)) : Infinity;
}

export function windowRows(rows: Row[], years = LOOKBACK_YEARS): Row[] {
  if (!rows.length) return [];
  const last = new Date(rows[rows.length - 1].date + "T00:00:00Z");
  last.setUTCDate(last.getUTCDate() - 365 * years);
  const cutoff = last.toISOString().slice(0, 10);
  return rows.filter((r) => r.date >= cutoff);
}

/** Share (0-100) of values <= x. Same definition as the Python side. */
export function percentileRank(sorted: number[], x: number): number {
  let lo = 0, hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] <= x) lo = mid + 1; else hi = mid;
  }
  return (100 * lo) / sorted.length;
}

/** Smallest value whose percentile rank is >= p. */
export function valueAtPercentile(sorted: number[], p: number): number {
  const idx = Math.max(0, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[idx];
}

export function classify(pct: number): Zone {
  if (pct <= BUY_PCT) return "BUY";
  if (pct >= EXPENSIVE_PCT) return "EXPENSIVE";
  return "NEUTRAL";
}

export type Stats = {
  date: string;
  pe: number;
  pb: number | null;
  divYield: number | null;
  zone: Zone;
  percentile: number;
  median: number;
  mean: number;
  zScore: number;
  buyBelow: number;     // PE level at the BUY threshold
  expensiveAbove: number;
  min: number;
  max: number;
  nPoints: number;
  capPe: number;        // PE above this is excluded from the statistics
  outlierDays: number;  // window days excluded
  change30d: number | null; // % change in PE vs ~30 calendar days ago
};

export function computeStats(rows: Row[]): Stats | null {
  const win = windowRows(rows);
  if (win.length < 2) return null;
  const capPe = outlierCap(win);
  const pes = win.map((r) => r.pe).filter((v) => v <= capPe);
  const sorted = [...pes].sort((a, b) => a - b);
  const today = win[win.length - 1];
  const mean = pes.reduce((a, b) => a + b, 0) / pes.length;
  const sd = Math.sqrt(pes.reduce((a, b) => a + (b - mean) ** 2, 0) / pes.length);
  const median = medianOf(pes);
  const pct = percentileRank(sorted, today.pe);

  const cutoff = new Date(today.date + "T00:00:00Z");
  cutoff.setUTCDate(cutoff.getUTCDate() - 30);
  const iso = cutoff.toISOString().slice(0, 10);
  const past = [...win].reverse().find((r) => r.date <= iso);

  return {
    date: today.date,
    pe: today.pe,
    pb: today.pb,
    divYield: today.div_yield,
    zone: classify(pct),
    percentile: Math.round(pct * 10) / 10,
    median,
    mean,
    zScore: sd ? (today.pe - mean) / sd : 0,
    buyBelow: valueAtPercentile(sorted, BUY_PCT),
    expensiveAbove: valueAtPercentile(sorted, EXPENSIVE_PCT),
    min: sorted[0],
    max: sorted[sorted.length - 1],
    nPoints: win.length,
    capPe,
    outlierDays: win.length - pes.length,
    change30d: past ? ((today.pe - past.pe) / past.pe) * 100 : null,
  };
}

export function histogram(rows: Row[]) {
  const win = windowRows(rows);
  const cap = outlierCap(win);
  const pes = win.map((r) => r.pe).filter((v) => v <= cap);
  if (!pes.length) return [];
  const span = Math.max(...pes) - Math.min(...pes);
  const binSize = span > 60 ? 5 : span > 25 ? 2 : 1;
  const lo = Math.floor(Math.min(...pes) / binSize) * binSize;
  const hi = Math.ceil(Math.max(...pes) / binSize) * binSize || lo + binSize;
  const bins: { from: number; to: number; count: number }[] = [];
  for (let x = lo; x < hi; x += binSize) bins.push({ from: x, to: x + binSize, count: 0 });
  for (const v of pes) {
    const i = Math.min(bins.length - 1, Math.floor((v - lo) / binSize));
    bins[i].count++;
  }
  return bins;
}

export const RANGES = [
  { key: "1Y", days: 365 },
  { key: "3Y", days: 365 * 3 },
  { key: "5Y", days: 365 * 5 },
  { key: "10Y", days: 365 * 10 },
  { key: "All", days: Infinity },
] as const;

export function sliceRange<T extends { date: string }>(rows: T[], days: number): T[] {
  if (!rows.length || !isFinite(days)) return rows;
  const last = new Date(rows[rows.length - 1].date + "T00:00:00Z");
  last.setUTCDate(last.getUTCDate() - days);
  const cutoff = last.toISOString().slice(0, 10);
  return rows.filter((r) => r.date >= cutoff);
}
