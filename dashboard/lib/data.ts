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

export type StockItem = {
  rank: number; symbol: string; name: string; industry: string; score: number; price: number; date: string;
  ret_1m: number | null; ret_3m: number | null; ret_6m: number | null; ret_12m: number | null;
  vs_200dma: number; drawdown: number; near_high: number; vol_surge: number | null;
  uptrend: boolean; on_sale: boolean; spark: number[];
};
export type StocksData = {
  date: string; universe: string; count: number; failures: string[];
  weights: Record<string, number>; sectors: { industry: string; n: number; score: number; ret_3m: number | null }[];
  items: StockItem[];
};
export type Strat = { paid: number; value: number; multiple: number; xirr: number | null; cash_left: number };
export type PlannerData = {
  advice: {
    date: string; sip: number; zone: Zone; pe_percentile: number; base_amount: number; drawdown: number;
    extra_multiple: number; extra_amount: number; total_amount: number; nifty: number; high_52w: number;
    zone_extra: number; max_extra: number; note: string;
    dip_levels: { drawdown: number; extra: number; nifty_level: number }[];
  };
  backtest: {
    from: string; to: string; months: number; sip: number;
    summary: { plain: Strat; scaled: Strat; core_plus: Strat };
    extra: { paid: number; value: number; buys: number; xirr: number | null };
    series: { date: string; paid: number; paid_plus: number; plain: number; scaled: number; core_plus: number }[];
  };
};
export const loadStocks = () => getJson<StocksData>("/data/stocks.json");
export const loadPlanner = () => getJson<PlannerData>("/data/planner.json");

export type MFScheme = { code: string; name: string; category: string; nav: number; date: string };
export type MFData = { date: string; count: number; schemes: MFScheme[] };
export type EarningsItem = { symbol: string; company: string; purpose: string; date: string };
export type EarningsData = { date: string; horizon_days: number; count: number; items: EarningsItem[] };
export const loadMF = () => getJson<MFData>("/data/mf.json");
export const loadEarnings = () => getJson<EarningsData>("/data/earnings.json");
