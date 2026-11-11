"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { StockItem, StocksData, loadStocks } from "../lib/data";
import { fmtFull } from "../lib/ui";
import Shell from "./Shell";

type SortKey = "score" | "ret_1m" | "ret_3m" | "ret_6m" | "drawdown" | "vol_surge";
type View = "hot" | "sale";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "score", label: "Hot score" },
  { key: "ret_1m", label: "1 month" },
  { key: "ret_3m", label: "3 months" },
  { key: "ret_6m", label: "6 months" },
  { key: "vol_surge", label: "Volume surge" },
  { key: "drawdown", label: "Furthest below high" },
];

const pct = (v: number | null, d = 1) => (v == null ? "n/a" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`);
const tone = (v: number | null) => (v == null ? "var(--text-muted)" : v >= 0 ? "var(--good-text)" : "var(--critical)");

function Spark({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return null;
  const w = 88, h = 26;
  const min = Math.min(...data), max = Math.max(...data), span = max - min || 1;
  const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - 2 - ((v - min) / span) * (h - 4)).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={up ? "Price rising over 6 months" : "Price falling over 6 months"}>
      <polyline points={pts} fill="none" stroke={up ? "var(--good)" : "var(--critical)"} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

export default function Stocks() {
  const [data, setData] = useState<StocksData | null>(null);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<View>("hot");
  const [sort, setSort] = useState<SortKey>("score");
  const [industry, setIndustry] = useState("All");
  const [q, setQ] = useState("");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => { loadStocks().then(setData).catch(() => setFailed(true)); }, []);

  const rows = useMemo(() => {
    if (!data) return [] as StockItem[];
    let r = data.items.filter((i) => (view === "sale" ? i.on_sale : true));
    if (industry !== "All") r = r.filter((i) => i.industry === industry);
    if (q.trim()) {
      const s = q.trim().toLowerCase();
      r = r.filter((i) => i.symbol.toLowerCase().includes(s) || i.name.toLowerCase().includes(s));
    }
    const val = (i: StockItem) => (sort === "drawdown" ? -i.drawdown : (i[sort] as number | null) ?? -Infinity);
    return [...r].sort((a, b) => val(b) - val(a));
  }, [data, view, sort, industry, q]);

  if (failed) {
    return (
      <Shell>
        <div className="card p-8">
          <h2 className="text-xl font-semibold">No stock data yet</h2>
          <p className="mt-2 text-[var(--text-secondary)]">Run <code>python -m tracker.run stocks</code>, or wait for the next daily workflow run.</p>
        </div>
      </Shell>
    );
  }
  if (!data) return <Shell><p className="text-[var(--text-secondary)]">Loading…</p></Shell>;

  const industries = ["All", ...[...new Set(data.items.map((i) => i.industry))].sort()];
  const shown = showAll || rows.length <= 25 ? rows : rows.slice(0, 25);
  const nSale = data.items.filter((i) => i.on_sale).length;
  const nUp = data.items.filter((i) => i.uptrend).length;

  return (
    <Shell>
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="card p-6">
        <h2 className="text-lg font-semibold">What the market is buying</h2>
        <p className="text-sm text-[var(--text-secondary)]">
          {data.universe}, {data.count} stocks, as of {fmtFull(data.date)}. Ranked by momentum and volume. This shows what is hot, not what is cheap.
        </p>
        <ul className="mt-4 space-y-2 text-[15px]">
          <li className="flex gap-2"><span aria-hidden className="text-[var(--text-muted)]">•</span><span>Hottest: {data.items.slice(0, 5).map((i) => i.symbol).join(", ")}.</span></li>
          <li className="flex gap-2"><span aria-hidden className="text-[var(--text-muted)]">•</span><span>Hottest sectors: {data.sectors.slice(0, 3).map((s) => `${s.industry} (${pct(s.ret_3m)} over 3 months)`).join("; ")}.</span></li>
          <li className="flex gap-2"><span aria-hidden className="text-[var(--text-muted)]">•</span><span>{nUp} of {data.count} trade above their 200-day average. {nSale} are 15% or more below their 52-week high.</span></li>
        </ul>
      </motion.section>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="View" className="flex gap-1">
          {([["hot", "Hot list"], ["sale", `On sale (${nSale})`]] as [View, string][]).map(([k, l]) => (
            <button key={k} onClick={() => { setView(k); setSort(k === "sale" ? "drawdown" : "score"); setShowAll(false); }} aria-pressed={view === k}
              className="rounded-lg border border-[var(--border)] px-3 py-1 text-sm aria-pressed:bg-[var(--text-primary)] aria-pressed:text-[var(--surface)]">{l}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <label className="sr-only" htmlFor="q">Search stocks</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" className="rounded-lg border border-[var(--border)] bg-transparent px-3 py-1" />
          <label className="sr-only" htmlFor="ind">Sector</label>
          <select id="ind" value={industry} onChange={(e) => setIndustry(e.target.value)} className="rounded-lg border border-[var(--border)] bg-transparent px-2 py-1">
            {industries.map((i) => <option key={i} value={i}>{i === "All" ? "All sectors" : i}</option>)}
          </select>
          <label className="sr-only" htmlFor="sort">Sort by</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="rounded-lg border border-[var(--border)] bg-transparent px-2 py-1">
            {SORTS.map((s) => <option key={s.key} value={s.key}>Sort: {s.label}</option>)}
          </select>
        </div>
      </div>
      {view === "sale" && (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Large caps well below their 52-week high. A fall can mean a bargain or a real problem, so check why before buying. Use this as a shortlist, not a buy list.
        </p>
      )}

      <div className="card mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">Stocks ranked by hot score</caption>
          <thead>
            <tr className="text-left text-[var(--text-secondary)]">
              <th className="p-3">#</th><th className="p-3">Stock</th><th className="p-3">Score</th>
              <th className="p-3">1M</th><th className="p-3">3M</th><th className="p-3">6M</th>
              <th className="p-3">From 52w high</th><th className="p-3">Volume</th><th className="p-3">6-month price</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((s) => (
              <tr key={s.symbol} className="border-t border-[var(--border)]">
                <td className="p-3 tabular-nums text-[var(--text-muted)]">{s.rank}</td>
                <td className="p-3">
                  <div className="font-medium">{s.symbol}</div>
                  <div className="text-xs text-[var(--text-secondary)]">{s.name}</div>
                </td>
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-16 rounded-full bg-[var(--grid)]" aria-hidden><div className="h-2 rounded-full" style={{ width: `${s.score}%`, background: "var(--series-1)" }} /></div>
                    <span className="w-8 tabular-nums">{s.score.toFixed(0)}</span>
                  </div>
                </td>
                <td className="p-3 tabular-nums" style={{ color: tone(s.ret_1m) }}>{pct(s.ret_1m)}</td>
                <td className="p-3 tabular-nums" style={{ color: tone(s.ret_3m) }}>{pct(s.ret_3m)}</td>
                <td className="p-3 tabular-nums" style={{ color: tone(s.ret_6m) }}>{pct(s.ret_6m)}</td>
                <td className="p-3 tabular-nums">{s.drawdown > -0.05 ? "at high" : pct(s.drawdown)}</td>
                <td className="p-3 tabular-nums">{s.vol_surge == null ? "n/a" : `${s.vol_surge.toFixed(1)}x`}</td>
                <td className="p-3"><Spark data={s.spark} up={s.spark[s.spark.length - 1] >= s.spark[0]} /></td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={9} className="p-6 text-center text-[var(--text-secondary)]">No stocks match.</td></tr>}
          </tbody>
        </table>
      </div>
      {rows.length > 25 && (
        <button onClick={() => setShowAll(!showAll)} className="mt-3 rounded-lg border border-[var(--border)] px-3 py-1 text-sm">
          {showAll ? "Show top 25" : `Show all ${rows.length}`}
        </button>
      )}

      <h2 className="mt-8 text-lg font-semibold">Sectors by heat</h2>
      <p className="text-sm text-[var(--text-secondary)]">Average hot score of the stocks in each sector.</p>
      <div className="card mt-3 space-y-2 p-4">
        {data.sectors.map((s) => (
          <div key={s.industry} className="flex items-center gap-3 text-sm">
            <span className="w-44 shrink-0 truncate" title={s.industry}>{s.industry} <span className="text-[var(--text-muted)]">({s.n})</span></span>
            <div className="h-2 flex-1 rounded-full bg-[var(--grid)]" aria-hidden><div className="h-2 rounded-full" style={{ width: `${s.score}%`, background: "var(--series-1)" }} /></div>
            <span className="w-10 text-right tabular-nums">{s.score.toFixed(0)}</span>
            <span className="w-16 text-right tabular-nums" style={{ color: tone(s.ret_3m) }}>{pct(s.ret_3m)}</span>
          </div>
        ))}
      </div>

      <footer className="mt-10 border-t border-[var(--border)] pt-4 text-xs text-[var(--text-muted)]">
        Score (0 to 100) = ranks of 1M return 20%, 3M return 30%, 6M return 15%, volume surge (10-day vs 60-day average) 15% and closeness to the 52-week high 20%.
        Prices from Yahoo Finance, constituents from niftyindices. Momentum can reverse fast. Signal only, not financial advice.
      </footer>
    </Shell>
  );
}
