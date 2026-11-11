"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PlannerData, Strat, loadPlanner } from "../lib/data";
import { ZONE_UI, fmtDate, fmtFull } from "../lib/ui";
import Shell from "./Shell";

const inr = (v: number) => "₹" + Math.round(v).toLocaleString("en-IN");
const lakh = (v: number) => (v >= 1e7 ? `${(v / 1e7).toFixed(1)}Cr` : `${(v / 1e5).toFixed(0)}L`);

export default function Planner() {
  const [d, setD] = useState<PlannerData | null>(null);
  const [failed, setFailed] = useState(false);
  const [sip, setSip] = useState(12000);

  useEffect(() => { loadPlanner().then((p) => { setD(p); setSip(p.advice.sip); }).catch(() => setFailed(true)); }, []);

  const a = d?.advice;
  // Scale the saved ₹12k plan to whatever monthly amount is typed; the multiples are what the rule decides.
  const calc = useMemo(() => {
    if (!a) return null;
    const extra = sip * a.extra_multiple;
    return { base: sip, extra, total: sip + extra, zoneExtra: sip * (a.zone_extra / a.sip), max: sip * (a.max_extra / a.sip) };
  }, [a, sip]);

  if (failed) {
    return (
      <Shell>
        <div className="card p-8">
          <h2 className="text-xl font-semibold">No planner data yet</h2>
          <p className="mt-2 text-[var(--text-secondary)]">Run <code>python -m tracker.run stocks</code>, or wait for the next daily workflow run.</p>
        </div>
      </Shell>
    );
  }
  if (!d || !a || !calc) return <Shell><p className="text-[var(--text-secondary)]">Loading…</p></Shell>;

  const z = ZONE_UI[a.zone];
  const bt = d.backtest;
  const rows: { key: keyof PlannerData["backtest"]["summary"]; name: string; note: string }[] = [
    { key: "plain", name: "Plain SIP", note: "Same amount every month." },
    { key: "core_plus", name: "SIP + extra when cheap or down", note: "SIP never changes. Extra money added in the BUY zone or after 10%+ falls." },
    { key: "scaled", name: "Cut SIP when expensive (rejected)", note: "Half the SIP when expensive, double when cheap, same total budget." },
  ];

  return (
    <Shell>
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">This month</h2>
            <p className="text-sm text-[var(--text-secondary)]">Nifty 50 as of {fmtFull(a.date)}. Level {a.nifty.toLocaleString("en-IN")}, {Math.abs(a.drawdown).toFixed(1)}% below its 52-week high.</p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm" style={{ background: "var(--grid)" }}>
            <span aria-hidden style={{ color: z.color }}>{z.icon}</span>{z.label} (PE percentile {a.pe_percentile.toFixed(0)})
          </span>
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="sip" className="text-sm text-[var(--text-secondary)]">Monthly SIP</label>
            <input id="sip" type="number" min={500} step={500} value={sip} onChange={(e) => setSip(Math.max(0, Number(e.target.value) || 0))}
              className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-lg tabular-nums" />
          </div>
          <div>
            <div className="text-sm text-[var(--text-secondary)]">Regular SIP</div>
            <div className="mt-1 text-3xl font-semibold tabular-nums">{inr(calc.base)}</div>
          </div>
          <div>
            <div className="text-sm text-[var(--text-secondary)]">Extra from your opportunity fund</div>
            <div className="mt-1 text-3xl font-semibold tabular-nums" style={{ color: calc.extra > 0 ? "var(--good-text)" : undefined }}>{calc.extra > 0 ? "+" + inr(calc.extra) : "none"}</div>
          </div>
        </div>
        <p className="mt-4 text-[15px]">
          {calc.extra > 0
            ? <>Total this month: <strong>{inr(calc.total)}</strong>. The market is in the BUY zone{a.drawdown <= -10 ? " and well below its high" : ""}, so the rule adds extra on top of the SIP.</>
            : <>Invest your regular SIP and keep your opportunity fund for now. Nothing here says to add extra.</>}
        </p>

        <h3 className="mt-6 text-sm font-semibold">The rule</h3>
        <ul className="mt-2 space-y-1 text-sm text-[var(--text-secondary)]">
          <li>• Always invest the full SIP. Never skip it, even when the market is expensive.</li>
          <li>• Nifty 50 PE in the BUY zone (bottom 25% of 10 years): add {inr(calc.zoneExtra)} extra.</li>
          {a.dip_levels.map((l) => (
            <li key={l.drawdown}>• Nifty {Math.abs(l.drawdown)}% below its high (about {l.nifty_level.toLocaleString("en-IN")}): add {inr((sip * l.extra) / a.sip)} extra.</li>
          ))}
          <li>• Extra is capped at {inr(calc.max)} a month. {a.note}</li>
        </ul>
      </motion.section>

      <h2 className="mt-8 text-lg font-semibold">Did this work in the past?</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Monthly SIP of {inr(bt.sip)} on Nifty 50, {fmtFull(bt.from)} to {fmtFull(bt.to)} ({bt.months} months). Each month uses only what was known that day. Prices exclude dividends.
      </p>
      <div className="card mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <caption className="sr-only">Backtest results by strategy</caption>
          <thead><tr className="text-left text-[var(--text-secondary)]"><th className="p-3">Strategy</th><th className="p-3">Money put in</th><th className="p-3">Worth now</th><th className="p-3">Yearly return</th></tr></thead>
          <tbody>
            {rows.map((r) => {
              const s: Strat = bt.summary[r.key];
              return (
                <tr key={r.key} className="border-t border-[var(--border)] align-top">
                  <td className="p-3"><div className="font-medium">{r.name}</div><div className="text-xs text-[var(--text-secondary)]">{r.note}</div></td>
                  <td className="p-3 tabular-nums">{inr(s.paid)}</td>
                  <td className="p-3 tabular-nums">{inr(s.value)}</td>
                  <td className="p-3 tabular-nums">{s.xirr == null ? "n/a" : `${s.xirr.toFixed(1)}%`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ul className="mt-3 space-y-1 text-sm">
        <li>• The extra money alone ({bt.extra.buys} buys, {inr(bt.extra.paid)}) earned <strong>{bt.extra.xirr == null ? "n/a" : `${bt.extra.xirr.toFixed(1)}%`} a year</strong>, against {bt.summary.plain.xirr?.toFixed(1)}% for the plain SIP. A small edge, not a big one.</li>
        <li>• Cutting the SIP when expensive did worse ({bt.summary.scaled.xirr?.toFixed(1)}%), because expensive months did not do worse than average. That is why the rule never skips the SIP.</li>
        <li>• Caveat: the rule was chosen after looking at this same history, mostly one rising market, so the real future edge is likely smaller than shown.</li>
      </ul>

      <div className="card mt-3 p-4">
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={bt.series} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={fmtDate} minTickGap={56} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tick={{ className: "axis-tick" }} />
            <YAxis tickFormatter={lakh} tickLine={false} axisLine={false} width={48} tick={{ className: "axis-tick" }} />
            <Tooltip formatter={(v) => inr(Number(v))} labelFormatter={(l) => fmtFull(String(l))} />
            <Legend />
            <Line name="SIP + extra" type="monotone" dataKey="core_plus" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line name="Plain SIP" type="monotone" dataKey="plain" stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line name="Cut when expensive" type="monotone" dataKey="scaled" stroke="var(--text-muted)" strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            <Line name="Money in (plain)" type="monotone" dataKey="paid" stroke="var(--axis)" strokeWidth={1} strokeDasharray="2 3" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-[var(--text-muted)]">Value of each approach over time. SIP + extra has put in more money in total ({inr(bt.summary.core_plus.paid)} vs {inr(bt.summary.plain.paid)}), so compare yearly return, not the end value.</p>
      </div>

      <h2 className="mt-8 text-lg font-semibold">About intraday</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        This tool does not give intraday signals. Valuation and momentum move over weeks and months, and most retail intraday traders lose money after costs. If the market falls hard, use the dip levels above for investing instead.
      </p>

      <footer className="mt-10 border-t border-[var(--border)] pt-4 text-xs text-[var(--text-muted)]">
        Prices from Yahoo Finance, PE from niftyindices. Past results do not predict future returns. Signal only, not financial advice.
      </footer>
    </Shell>
  );
}
