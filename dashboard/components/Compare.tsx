"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Compare as CompareData, Meta, Relative, TableRow, loadCompare, loadHistory, loadMeta, relativeSeries } from "../lib/data";
import { RANGES, Row, percentileRank, sliceRange, valueAtPercentile, windowRows } from "../lib/stats";
import { ZONE_UI, fmtDate, fmtFull } from "../lib/ui";
import Shell from "./Shell";

export default function Compare() {
  const [data, setData] = useState<CompareData | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    Promise.all([loadCompare(), loadMeta()]).then(([c, m]) => { setData(c); setMeta(m); }).catch(() => setFailed(true));
  }, []);

  if (failed || (data && !data.table.length)) {
    return (
      <Shell>
        <div className="card p-8">
          <h2 className="text-xl font-semibold">No comparison data yet</h2>
          <p className="mt-2 text-[var(--text-secondary)]">
            Run <code>python -m tracker.run backfill</code> then <code>python -m tracker.run daily</code> (or <code>demo</code> for synthetic data).
          </p>
        </div>
      </Shell>
    );
  }
  if (!data) return <Shell><p className="text-[var(--text-secondary)]">Loading…</p></Shell>;

  const label = (k: string) => data.table.find((t) => t.key === k)?.label ?? k;

  return (
    <Shell>
      {meta?.demo && (
        <div role="status" className="mb-6 rounded-xl border border-[var(--series-2)] px-4 py-3 text-sm">
          <strong>Demo mode.</strong> This is synthetic data for previewing the UI, not the real market.
        </div>
      )}

      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="card p-6">
        <h2 className="text-lg font-semibold">What the numbers say</h2>
        <p className="text-sm text-[var(--text-secondary)]">Rule-based reading of valuation history{data.date ? ` as of ${fmtFull(data.date)}` : ""}. Not a price forecast.</p>
        <ul className="mt-4 space-y-2 text-[15px]">
          {data.insights.map((t, i) => (
            <li key={i} className="flex gap-2"><span aria-hidden className="text-[var(--text-muted)]">•</span><span>{t}</span></li>
          ))}
        </ul>
      </motion.section>

      <h2 className="mt-8 text-lg font-semibold">Ranked: cheapest to richest vs own history</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Valuation score is the average of the PE percentile, PB percentile and (inverted) dividend-yield percentile over 10 years. Lower is cheaper. The zone follows PE percentile, the same rule as your alerts.
      </p>
      <RankTable rows={data.table} />

      <RelativeSection rels={data.relative} label={label} />

      <h2 className="mt-8 text-lg font-semibold">Do they move together?</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Correlation of daily PE changes over the last {data.correlation.years} years. Blue is moving together, red is moving opposite. Lower values mean better diversification.
      </p>
      <Heatmap corr={data.correlation} label={label} />

      <footer className="mt-10 border-t border-[var(--border)] pt-4 text-xs text-[var(--text-muted)]">
        Source: {meta?.source}. Index PE methods differ slightly, so cross-index comparisons are approximate. Signal only, not financial advice.
      </footer>
    </Shell>
  );
}

function Bar({ value, marks }: { value: number | null; marks?: number[] }) {
  if (value == null) return <span className="text-[var(--text-muted)]">n/a</span>;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-24 rounded-full bg-[var(--grid)]" aria-hidden>
        <div className="h-2 rounded-full" style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: "var(--series-1)" }} />
        {marks?.map((m) => <span key={m} className="absolute top-[-2px] h-3 w-px bg-[var(--text-muted)]" style={{ left: `${m}%` }} />)}
      </div>
      <span className="w-8 tabular-nums">{value.toFixed(0)}</span>
    </div>
  );
}

function RankTable({ rows }: { rows: TableRow[] }) {
  return (
    <div className="card mt-3 overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <caption className="sr-only">Indices ranked by valuation score, cheapest first</caption>
        <thead>
          <tr className="text-left text-[var(--text-secondary)]">
            <th className="p-3">Index</th><th className="p-3">PE</th><th className="p-3">PE percentile</th>
            <th className="p-3">Valuation score</th><th className="p-3">PB</th><th className="p-3">Div. yield</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const z = ZONE_UI[r.zone];
            return (
              <tr key={r.key} className="border-t border-[var(--border)]">
                <td className="p-3">
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden style={{ color: z.color }}>{z.icon}</span>
                    <a className="font-medium underline-offset-2 hover:underline" href={`/#${r.key}`}>{r.label}</a>
                    <span className="text-xs text-[var(--text-secondary)]">{z.label}</span>
                  </span>
                </td>
                <td className="p-3 tabular-nums">{r.pe.toFixed(1)}</td>
                <td className="p-3"><Bar value={r.pe_percentile} marks={[25, 75]} /></td>
                <td className="p-3"><Bar value={r.composite} /></td>
                <td className="p-3 tabular-nums">{r.pb?.toFixed(2) ?? "n/a"}</td>
                <td className="p-3 tabular-nums">{r.div_yield != null ? r.div_yield.toFixed(2) + "%" : "n/a"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RelativeSection({ rels, label }: { rels: Relative[]; label: (k: string) => string }) {
  const [sel, setSel] = useState(0);
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("5Y");
  const [series, setSeries] = useState<{ date: string; premium: number }[] | null>(null);
  const rel = rels[sel];

  useEffect(() => {
    if (!rel) return;
    setSeries(null);
    Promise.all([loadHistory(rel.a), loadHistory(rel.b)])
      .then(([a, b]: [Row[], Row[]]) => setSeries(relativeSeries(windowRows(a), windowRows(b))))
      .catch(() => setSeries([]));
  }, [rel?.a, rel?.b]);

  const bands = useMemo(() => {
    if (!series?.length) return null;
    const sorted = series.map((s) => s.premium).sort((x, y) => x - y);
    return { lo: valueAtPercentile(sorted, 25), hi: valueAtPercentile(sorted, 75), med: sorted[sorted.length >> 1], today: sorted.length ? percentileRank(sorted, series[series.length - 1].premium) : 0 };
  }, [series]);
  const visible = useMemo(() => (series ? sliceRange(series, RANGES.find((r) => r.key === range)!.days) : []), [series, range]);

  if (!rels.length) return null;
  return (
    <>
      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Relative valuation</h2>
          <p className="text-sm text-[var(--text-secondary)]">PE premium (+) or discount (−) of an index over Nifty 50. A low reading means it is cheap vs large caps by its own history.</p>
        </div>
        <div role="group" aria-label="Time range" className="flex gap-1">
          {RANGES.map((r) => (
            <button key={r.key} onClick={() => setRange(r.key)} aria-pressed={range === r.key}
              className="rounded-lg border border-[var(--border)] px-3 py-1 text-sm aria-pressed:bg-[var(--text-primary)] aria-pressed:text-[var(--surface)]">{r.key}</button>
          ))}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2" role="tablist" aria-label="Pair">
        {rels.map((r, i) => (
          <button key={r.a + r.b} role="tab" aria-selected={sel === i} onClick={() => setSel(i)}
            className="rounded-full border border-[var(--border)] px-3 py-1 text-sm aria-selected:bg-[var(--text-primary)] aria-selected:text-[var(--surface)]">
            {label(r.a)} vs {label(r.b)}
          </button>
        ))}
      </div>
      <div className="card mt-3 p-4">
        <p className="mb-2 text-sm">
          Now <strong>{rel.premium >= 0 ? "+" : ""}{rel.premium.toFixed(1)}%</strong> · 10y median {rel.median.toFixed(1)}% · percentile {rel.percentile.toFixed(0)}
          {rel.percentile <= 25 ? " (unusually low)" : rel.percentile >= 75 ? " (unusually high)" : ""}
        </p>
        {series === null ? <p className="text-[var(--text-secondary)]">Loading…</p> : (
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={visible} margin={{ top: 8, right: 96, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tickFormatter={fmtDate} minTickGap={56} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={{ className: "axis-tick" }} />
              <YAxis tickFormatter={(v) => `${Number(v).toFixed(0)}%`} tickLine={false} axisLine={false} width={48} tick={{ className: "axis-tick" }} />
              <ReferenceLine y={0} stroke="var(--axis)" />
              {bands && <>
                <ReferenceLine y={bands.lo} stroke="var(--good)" strokeDasharray="4 4" label={{ value: `Low ${bands.lo.toFixed(0)}%`, position: "right", className: "axis-tick" }} />
                <ReferenceLine y={bands.med} stroke="var(--text-muted)" strokeDasharray="2 4" label={{ value: `Median ${bands.med.toFixed(0)}%`, position: "right", className: "axis-tick" }} />
                <ReferenceLine y={bands.hi} stroke="var(--critical)" strokeDasharray="4 4" label={{ value: `High ${bands.hi.toFixed(0)}%`, position: "right", className: "axis-tick" }} />
              </>}
              <Tooltip content={<RelTip />} cursor={{ stroke: "var(--text-muted)" }} />
              <Line type="monotone" dataKey="premium" stroke="var(--series-1)" strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        <p className="mt-2 text-xs text-[var(--text-muted)]">Dashed lines are the 25th and 75th percentile of the 10-year premium.</p>
      </div>
    </>
  );
}

function RelTip({ active, payload }: { active?: boolean; payload?: { payload: { date: string; premium: number } }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tt">
      <div className="font-semibold">{fmtFull(p.date)}</div>
      <div>{p.premium >= 0 ? "▲" : "▼"} {Math.abs(p.premium).toFixed(1)}% {p.premium >= 0 ? "premium" : "discount"}</div>
    </div>
  );
}

function Heatmap({ corr, label }: { corr: CompareData["correlation"]; label: (k: string) => string }) {
  const { keys, matrix } = corr;
  return (
    <div className="card mt-3 overflow-x-auto p-3">
      <table className="w-full min-w-[640px] border-separate border-spacing-1 text-xs">
        <caption className="sr-only">Correlation matrix of daily PE changes</caption>
        <thead>
          <tr><th />{keys.map((k) => <th key={k} scope="col" className="px-1 pb-1 text-center font-medium text-[var(--text-secondary)]">{label(k).replace("Nifty ", "")}</th>)}</tr>
        </thead>
        <tbody>
          {keys.map((a, i) => (
            <tr key={a}>
              <th scope="row" className="pr-2 text-right font-medium text-[var(--text-secondary)]">{label(a).replace("Nifty ", "")}</th>
              {keys.map((b, j) => {
                const v = matrix[i][j];
                const pct = v == null ? 0 : Math.round(Math.abs(v) * 70);
                return (
                  <td key={b} className="h-9 rounded-md text-center tabular-nums"
                    style={{ background: v == null ? "transparent" : `color-mix(in srgb, ${v >= 0 ? "var(--div-cool)" : "var(--div-warm)"} ${pct}%, var(--surface))` }}
                    title={`${label(a)} vs ${label(b)}: ${v ?? "n/a"}`}>
                    {v == null ? "n/a" : v.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
