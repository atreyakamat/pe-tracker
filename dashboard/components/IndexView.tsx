"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line,
  ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  RANGES, Row, computeStats, histogram, sliceRange, windowRows,
} from "../lib/stats";
import { IndexInfo, Latest, Meta, loadHistory, loadIndices, loadLatest, loadMeta } from "../lib/data";
import { ZONE_UI, fmtDate, fmtFull } from "../lib/ui";
import Shell from "./Shell";

export default function IndexView() {
  const [indices, setIndices] = useState<IndexInfo[] | null>(null);
  const [latest, setLatest] = useState<Latest>({});
  const [meta, setMeta] = useState<Meta | null>(null);
  const [key, setKey] = useState("nifty50");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("5Y");
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    Promise.all([loadIndices(), loadLatest(), loadMeta()])
      .then(([i, l, m]) => {
        setIndices(i); setLatest(l); setMeta(m);
        const h = window.location.hash.slice(1);
        setKey(i.some((x) => x.key === h) ? h : i.find((x) => x.key === "nifty50")?.key ?? i[0]?.key ?? "nifty50");
      })
      .catch(() => { setIndices([]); setMeta({ demo: false, source: "none", empty: true }); });
  }, []);

  useEffect(() => {
    if (!indices?.length) return;
    setRows(null);
    loadHistory(key).then(setRows).catch(() => setRows([]));
    window.history.replaceState(null, "", `#${key}`);
  }, [key, indices]);

  const label = indices?.find((i) => i.key === key)?.label ?? key;
  const stats = useMemo(() => (rows ? computeStats(rows) : null), [rows]);
  const visible = useMemo(() => {
    const days = RANGES.find((r) => r.key === range)!.days;
    return rows ? sliceRange(rows, days) : [];
  }, [rows, range]);
  const bins = useMemo(() => (rows ? histogram(rows) : []), [rows]);
  // Days flagged as earnings-collapse outliers are left as gaps, never plotted as spikes.
  const plotted = useMemo(
    () => visible.map((r) => ({ ...r, pe: stats && r.pe > stats.capPe ? null : r.pe })),
    [visible, stats],
  );
  const hiddenInView = useMemo(() => (stats ? visible.filter((r) => r.pe > stats.capPe).length : 0), [visible, stats]);
  const deviation = useMemo(() => {
    if (!stats) return [];
    return visible.map((r) => {
      if (r.pe > stats.capPe) return { date: r.date, above: null, below: null, d: null };
      const d = ((r.pe - stats.median) / stats.median) * 100;
      return { date: r.date, above: Math.max(d, 0), below: Math.min(d, 0), d };
    });
  }, [visible, stats]);

  if (indices === null || (indices.length > 0 && rows === null)) {
    return <Shell><p className="text-[var(--text-secondary)]">Loading…</p></Shell>;
  }
  if (!indices.length || !stats || meta?.empty) {
    return (
      <Shell>
        <div className="card p-8">
          <h2 className="text-xl font-semibold">No data yet</h2>
          <p className="mt-2 text-[var(--text-secondary)]">
            Run <code>python -m tracker.run backfill</code> then <code>python -m tracker.run daily</code>, or <code>python -m tracker.run demo</code> to preview with synthetic data.
          </p>
        </div>
      </Shell>
    );
  }

  const z = ZONE_UI[stats.zone];
  const cheaperThan = Math.round(100 - stats.percentile);

  return (
    <Shell>
      <div role="tablist" aria-label="Index" className="mb-6 flex flex-wrap gap-2">
        {indices.map((i) => {
          const zn = latest[i.key]?.zone;
          return (
            <button
              key={i.key}
              role="tab"
              aria-selected={key === i.key}
              onClick={() => setKey(i.key)}
              title={zn ? ZONE_UI[zn].label : undefined}
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] px-3 py-1 text-sm transition-colors aria-selected:bg-[var(--text-primary)] aria-selected:text-[var(--surface)]"
            >
              {zn && <span aria-hidden style={{ color: key === i.key ? undefined : ZONE_UI[zn].color }}>{ZONE_UI[zn].icon}</span>}
              {i.label}
              {zn && <span className="sr-only"> ({ZONE_UI[zn].label})</span>}
            </button>
          );
        })}
      </div>
      {meta?.demo && (
        <div role="status" className="mb-6 rounded-xl border border-[var(--series-2)] px-4 py-3 text-sm">
          <strong>Demo mode.</strong> This is synthetic data for previewing the UI, not the real market.
        </div>
      )}

      {/* Hero */}
      <motion.section
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
        className="card p-6 sm:p-8"
      >
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="text-sm text-[var(--text-secondary)]">{label} PE · {fmtFull(stats.date)}</p>
            <p className="mt-1 text-6xl font-semibold tracking-tight sm:text-7xl">{stats.pe.toFixed(2)}</p>
          </div>
          <div className="max-w-sm">
            <span
              className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold text-white"
              style={{ background: z.color }}
            >
              <span aria-hidden>{z.icon}</span> {z.label}
            </span>
            <p className="mt-3 text-sm text-[var(--text-secondary)]">{z.blurb}</p>
          </div>
        </div>
        <p className="mt-4 text-sm text-[var(--text-secondary)]">
          Cheaper than {cheaperThan}% of trading days in the last 10 years (percentile {stats.percentile.toFixed(0)}).
          Buy zone is PE ≤ {stats.buyBelow.toFixed(1)}; expensive is ≥ {stats.expensiveAbove.toFixed(1)}.
        </p>
      </motion.section>

      {/* KPI row */}
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { k: "10y median PE", v: stats.median.toFixed(2) },
          { k: "vs median", v: `${(((stats.pe - stats.median) / stats.median) * 100).toFixed(1)}%` },
          { k: "z-score", v: stats.zScore.toFixed(2) },
          { k: "Valuation score", v: latest[key]?.composite != null ? `${latest[key].composite!.toFixed(0)}/100` : "n/a" },
          { k: "30-day PE change", v: stats.change30d == null ? "n/a" : `${stats.change30d >= 0 ? "▲" : "▼"} ${Math.abs(stats.change30d).toFixed(1)}%` },
          { k: "PB · Div. yield", v: `${stats.pb?.toFixed(2) ?? "n/a"} · ${stats.divYield != null ? stats.divYield.toFixed(2) + "%" : "n/a"}` },
        ].map((t, i) => (
          <motion.div
            key={t.k} className="card p-4"
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i + 0.1 }}
          >
            <p className="text-xs text-[var(--text-secondary)]">{t.k}</p>
            <p className="mt-1 whitespace-nowrap text-lg font-semibold">{t.v}</p>
          </motion.div>
        ))}
      </div>

      {/* Range selector */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">PE over time</h2>
        <div role="group" aria-label="Time range" className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              aria-pressed={range === r.key}
              className="rounded-lg border border-[var(--border)] px-3 py-1 text-sm transition-colors aria-pressed:bg-[var(--text-primary)] aria-pressed:text-[var(--surface)]"
            >
              {r.key}
            </button>
          ))}
        </div>
      </div>

      {/* Main PE chart */}
      <div className="card mt-3 p-4">
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={plotted} margin={{ top: 12, right: 96, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={fmtDate} minTickGap={56} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={{ className: "axis-tick" }} />
            <YAxis domain={[(min: number) => Math.floor(min) - 1, (max: number) => Math.ceil(max) + 1]} allowDecimals={false} tickFormatter={(v) => Number(v).toFixed(0)} tickLine={false} axisLine={false} width={36} tick={{ className: "axis-tick" }} />
            <ReferenceArea y1={0} y2={stats.buyBelow} fill="var(--good)" fillOpacity={0.1} ifOverflow="hidden" />
            <ReferenceArea y1={stats.expensiveAbove} y2={1000} fill="var(--critical)" fillOpacity={0.08} ifOverflow="hidden" />
            <ReferenceLine y={stats.buyBelow} stroke="var(--good)" strokeDasharray="4 4" label={{ value: `Buy ≤ ${stats.buyBelow.toFixed(1)}`, position: "right", className: "axis-tick" }} />
            <ReferenceLine y={stats.median} stroke="var(--text-muted)" strokeDasharray="2 4" label={{ value: `Median ${stats.median.toFixed(1)}`, position: "right", className: "axis-tick" }} />
            <ReferenceLine y={stats.expensiveAbove} stroke="var(--critical)" strokeDasharray="4 4" label={{ value: `Rich ≥ ${stats.expensiveAbove.toFixed(1)}`, position: "right", className: "axis-tick" }} />
            <Tooltip content={<PeTooltip median={stats.median} />} cursor={{ stroke: "var(--text-muted)" }} />
            <Line type="monotone" dataKey="pe" stroke="var(--series-1)" strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-[var(--text-muted)]">Bands use the 25th / 75th percentile of the last 10 years, the same rule that triggers your Telegram alert.
          {stats.outlierDays > 0 && (
            <> {stats.outlierDays} day{stats.outlierDays === 1 ? "" : "s"} in the 10-year window ({hiddenInView} in this view) had PE above {stats.capPe.toFixed(0)} because earnings briefly collapsed. They are left out of the line and the statistics.</>
          )}
        </p>
      </div>

      {/* Fluctuation: distance from median */}
      <h2 className="mt-8 text-lg font-semibold">Fluctuation: how far from normal</h2>
      <p className="text-sm text-[var(--text-secondary)]">Percent above (red) or below (blue) the 10-year median PE. Below the line is where you buy.</p>
      <div className="card mt-3 p-4">
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={deviation} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={fmtDate} minTickGap={56} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={{ className: "axis-tick" }} />
            <YAxis tickFormatter={(v) => `${Number(v).toFixed(0)}%`} tickLine={false} axisLine={false} width={44} tick={{ className: "axis-tick" }} />
            <ReferenceLine y={0} stroke="var(--axis)" />
            <Tooltip content={<DevTooltip />} cursor={{ stroke: "var(--text-muted)" }} />
            <Area type="monotone" dataKey="above" stroke="var(--div-warm)" strokeWidth={1.5} fill="var(--div-warm)" fillOpacity={0.3} isAnimationActive={false} />
            <Area type="monotone" dataKey="below" stroke="var(--div-cool)" strokeWidth={1.5} fill="var(--div-cool)" fillOpacity={0.3} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Distribution */}
      <h2 className="mt-8 text-lg font-semibold">Where today sits in the last 10 years</h2>
      <p className="text-sm text-[var(--text-secondary)]">Number of trading days at each PE level. Orange marks today's level.</p>
      <div className="card mt-3 p-4">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={bins} margin={{ top: 8, right: 16, bottom: 4, left: 0 }} barCategoryGap={2}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="from" tickFormatter={(v) => String(v)} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={{ className: "axis-tick" }} interval="preserveStartEnd" />
            <YAxis tickLine={false} axisLine={false} width={36} tick={{ className: "axis-tick" }} />
            <Tooltip content={<BinTooltip />} cursor={{ fill: "var(--grid)", opacity: 0.4 }} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {bins.map((b) => (
                <Cell key={b.from} fill={stats.pe >= b.from && stats.pe < b.to ? "var(--series-2)" : "var(--series-1)"} fillOpacity={stats.pe >= b.from && stats.pe < b.to ? 1 : 0.55} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table view (accessibility + exact numbers) */}
      <div className="mt-8">
        <button onClick={() => setShowTable((s) => !s)} aria-expanded={showTable} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm">
          {showTable ? "Hide" : "Show"} data table
        </button>
        {showTable && <DataTable rows={windowRows(rows ?? []).slice(-30).reverse()} median={stats.median} />}
      </div>

      <footer className="mt-10 border-t border-[var(--border)] pt-4 text-xs text-[var(--text-muted)]">
        Source: {meta?.source}. Signal only, not financial advice. Valuation can stay cheap or rich for years, so use it to size extra buys, not to stop a SIP.
      </footer>
    </Shell>
  );
}

type TipProps = { active?: boolean; payload?: { payload: any }[] };

function PeTooltip({ active, payload, median }: TipProps & { median: number }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload as Row;
  const vs = ((r.pe - median) / median) * 100;
  return (
    <div className="tt">
      <div className="font-semibold">{fmtFull(r.date)}</div>
      <div>PE {r.pe.toFixed(2)}</div>
      <div className="text-[var(--text-secondary)]">{vs >= 0 ? "▲" : "▼"} {Math.abs(vs).toFixed(1)}% vs median</div>
    </div>
  );
}

function DevTooltip({ active, payload }: TipProps) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as { date: string; d: number };
  return (
    <div className="tt">
      <div className="font-semibold">{fmtFull(p.date)}</div>
      <div>{p.d >= 0 ? "▲" : "▼"} {Math.abs(p.d).toFixed(1)}% {p.d >= 0 ? "above" : "below"} median</div>
    </div>
  );
}

function BinTooltip({ active, payload }: TipProps) {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload as { from: number; to: number; count: number };
  return (
    <div className="tt">
      <div className="font-semibold">PE {b.from} to {b.to}</div>
      <div>{b.count} trading days</div>
    </div>
  );
}

function DataTable({ rows, median }: { rows: Row[]; median: number }) {
  return (
    <div className="card mt-3 overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Last 30 trading days of Nifty 50 valuation</caption>
        <thead>
          <tr className="text-left text-[var(--text-secondary)]">
            <th className="p-3">Date</th><th className="p-3">PE</th><th className="p-3">vs median</th><th className="p-3">PB</th><th className="p-3">Div. yield</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const vs = ((r.pe - median) / median) * 100;
            return (
              <tr key={r.date} className="border-t border-[var(--border)] tabular-nums">
                <td className="p-3">{fmtFull(r.date)}</td>
                <td className="p-3">{r.pe.toFixed(2)}</td>
                <td className="p-3">{vs >= 0 ? "▲" : "▼"} {Math.abs(vs).toFixed(1)}%</td>
                <td className="p-3">{r.pb?.toFixed(2) ?? "n/a"}</td>
                <td className="p-3">{r.div_yield != null ? r.div_yield.toFixed(2) + "%" : "n/a"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
