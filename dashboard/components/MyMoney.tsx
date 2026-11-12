"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  EarningsData, MFData, PlannerData, StocksData,
  loadEarnings, loadMF, loadPlanner, loadStocks,
} from "../lib/data";
import { fmtFull } from "../lib/ui";
import Shell from "./Shell";

/** Everything on this page lives in THIS browser's localStorage. Nothing is uploaded anywhere. */

type Holding = { id: string; kind: "stock" | "mf"; key: string; name: string; qty: number; cost: number };
type FundEntry = { id: string; date: string; amount: number; note: string }; // +ve added, -ve invested
type Saved = { holdings: Holding[]; fund: FundEntry[] };
type Row = {
  h: Holding; price: number | null | undefined; invested: number; value: number | null;
  pl: number | null; plPct: number | null; sector: string; onSale: boolean;
  drawdown?: number; results?: string; asOf?: string;
};

const KEY = "pe-tracker:money:v1";
const EMPTY: Saved = { holdings: [], fund: [] };

function load(): Saved {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const p = JSON.parse(raw);
    return { holdings: Array.isArray(p.holdings) ? p.holdings : [], fund: Array.isArray(p.fund) ? p.fund : [] };
  } catch {
    return EMPTY;
  }
}
function save(s: Saved) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode etc. — keep going in memory */ }
}

const inr = (v: number) => "₹" + Math.round(v).toLocaleString("en-IN");
const signedInr = (v: number) => (v >= 0 ? "+" : "−") + inr(Math.abs(v));
const pctf = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const tone = (v: number) => (v >= 0 ? "var(--good-text)" : "var(--critical)");
const uid = () => Math.random().toString(36).slice(2, 10);
const today = () => new Date().toISOString().slice(0, 10);

export default function MyMoney() {
  const [stocks, setStocks] = useState<StocksData | null>(null);
  const [mf, setMF] = useState<MFData | null>(null);
  const [planner, setPlanner] = useState<PlannerData | null>(null);
  const [earnings, setEarnings] = useState<EarningsData | null>(null);
  const [saved, setSaved] = useState<Saved | null>(null);

  useEffect(() => {
    setSaved(load());
    loadStocks().then(setStocks).catch(() => setStocks(null));
    loadMF().then(setMF).catch(() => setMF(null));
    loadPlanner().then(setPlanner).catch(() => setPlanner(null));
    loadEarnings().then(setEarnings).catch(() => setEarnings(null));
  }, []);

  const update = (fn: (s: Saved) => Saved) => setSaved((s) => { const n = fn(s ?? EMPTY); save(n); return n; });

  const stockBy = useMemo(() => new Map((stocks?.items ?? []).map((i) => [i.symbol, i])), [stocks]);
  const mfBy = useMemo(() => new Map((mf?.schemes ?? []).map((m) => [m.code, m])), [mf]);
  const nextResult = useMemo(() => {
    const m = new Map<string, string>();
    for (const e of earnings?.items ?? []) if (!m.has(e.symbol)) m.set(e.symbol, e.date);
    return m;
  }, [earnings]);

  const rows: Row[] = useMemo(() => (saved?.holdings ?? []).map((h) => {
    const live = h.kind === "stock" ? stockBy.get(h.key) : undefined;
    const scheme = h.kind === "mf" ? mfBy.get(h.key) : undefined;
    const price = h.kind === "stock" ? live?.price : scheme?.nav;
    const invested = h.qty * h.cost;
    const value = price != null ? h.qty * price : null;
    return {
      h, price, invested, value,
      pl: value != null ? value - invested : null,
      plPct: value != null && invested > 0 ? ((value - invested) / invested) * 100 : null,
      sector: h.kind === "stock" ? (live?.industry ?? "Stocks") : "Index funds",
      onSale: h.kind === "stock" ? (live?.on_sale ?? false) : false,
      drawdown: h.kind === "stock" ? live?.drawdown : undefined,
      results: h.kind === "stock" ? nextResult.get(h.key) : undefined,
      asOf: h.kind === "stock" ? live?.date : scheme?.date,
    };
  }), [saved, stockBy, mfBy, nextResult]);

  const tot = useMemo(() => {
    const invested = rows.reduce((a, r) => a + r.invested, 0);
    const value = rows.reduce((a, r) => a + (r.value ?? r.invested), 0);
    const priced = rows.filter((r) => r.value != null).length;
    return { invested, value, pl: value - invested, priced };
  }, [rows]);

  const alloc = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.sector, (m.get(r.sector) ?? 0) + (r.value ?? r.invested));
    const total = [...m.values()].reduce((a, b) => a + b, 0) || 1;
    return [...m.entries()].map(([k, v]) => ({ sector: k, value: v, share: (v / total) * 100 }))
      .sort((a, b) => b.value - a.value);
  }, [rows]);

  const fundBalance = useMemo(() => (saved?.fund ?? []).reduce((a, e) => a + e.amount, 0), [saved]);

  if (!saved) return <Shell><p className="text-[var(--text-secondary)]">Loading…</p></Shell>;

  return (
    <Shell>
      <p className="mb-6 rounded-xl border border-[var(--border)] px-4 py-3 text-sm text-[var(--text-secondary)]">
        🔒 Everything you enter here is saved only in this browser on this device. It is never uploaded, so clear your browser data and it is gone — use Export for a backup.
      </p>

      {/* Summary */}
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4 sm:grid-cols-4">
        {[
          { l: "Money put in", v: inr(tot.invested) },
          { l: "Worth now", v: inr(tot.value) },
          { l: "Profit / loss", v: signedInr(tot.pl), c: tone(tot.pl) },
          { l: "Return", v: tot.invested > 0 ? pctf((tot.pl / tot.invested) * 100) : "—", c: tone(tot.pl) },
        ].map((t) => (
          <div key={t.l} className="card p-4">
            <div className="text-sm text-[var(--text-secondary)]">{t.l}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums" style={{ color: t.c }}>{t.v}</div>
          </div>
        ))}
      </motion.section>

      <HoldingsSection rows={rows} stocks={stocks} mf={mf} onAdd={(h) => update((s) => ({ ...s, holdings: [...s.holdings, h] }))}
        onRemove={(id) => update((s) => ({ ...s, holdings: s.holdings.filter((x) => x.id !== id) }))} />

      {alloc.length > 0 && (
        <>
          <h2 className="mt-8 text-lg font-semibold">Where your money sits</h2>
          <div className="card mt-3 space-y-2 p-4">
            {alloc.map((a) => (
              <div key={a.sector} className="flex items-center gap-3 text-sm">
                <span className="w-44 shrink-0 truncate" title={a.sector}>{a.sector}</span>
                <div className="h-2 flex-1 rounded-full bg-[var(--grid)]" aria-hidden>
                  <div className="h-2 rounded-full" style={{ width: `${Math.max(2, a.share)}%`, background: "var(--series-1)" }} />
                </div>
                <span className="w-12 text-right tabular-nums">{a.share.toFixed(0)}%</span>
                <span className="w-24 text-right tabular-nums text-[var(--text-secondary)]">{inr(a.value)}</span>
              </div>
            ))}
          </div>
          {(() => {
            const top = alloc.find((a) => a.sector !== "Index funds");
            return top && top.share > 40 && rows.length > 2 ? (
              <p className="mt-2 text-sm text-[var(--text-secondary)]">⚠ {top.share.toFixed(0)}% of your money is in {top.sector} stocks. That is a concentrated bet — fine if intended, risky if not. (Index funds are already diversified, so they are not counted here.)</p>
            ) : null;
          })()}
        </>
      )}

      <FundSection entries={saved.fund} balance={fundBalance} planner={planner}
        onAdd={(e) => update((s) => ({ ...s, fund: [...s.fund, e] }))}
        onRemove={(id) => update((s) => ({ ...s, fund: s.fund.filter((x) => x.id !== id) }))} />

      <EarningsSection earnings={earnings} held={new Set((saved.holdings).filter((h) => h.kind === "stock").map((h) => h.key))} />

      <BackupSection saved={saved} onImport={(s) => update(() => s)} />

      <footer className="mt-10 border-t border-[var(--border)] pt-4 text-xs text-[var(--text-muted)]">
        Stock prices and fund NAVs refresh each weekday evening. Values exclude brokerage, taxes and dividends. Signal only, not financial advice.
      </footer>
    </Shell>
  );
}

function HoldingsSection({ rows, stocks, mf, onAdd, onRemove }: {
  rows: Row[]; stocks: StocksData | null; mf: MFData | null;
  onAdd: (h: Holding) => void; onRemove: (id: string) => void;
}) {
  const [kind, setKind] = useState<"stock" | "mf">("stock");
  const [pick, setPick] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [err, setErr] = useState("");

  const options = useMemo(() => kind === "stock"
    ? (stocks?.items ?? []).map((i) => ({ key: i.symbol, label: `${i.symbol} — ${i.name}` }))
    : (mf?.schemes ?? []).map((m) => ({ key: m.code, label: `${m.name} (${m.code})` })), [kind, stocks, mf]);

  const add = () => {
    const opt = options.find((o) => o.label === pick || o.key === pick.trim().toUpperCase() || o.key === pick.trim());
    const q = Number(qty), c = Number(cost);
    if (!opt) return setErr(kind === "stock" ? "Pick a stock from the list (Nifty 100 only)." : "Pick a fund from the list (index funds only).");
    if (!(q > 0) || !(c > 0)) return setErr("Quantity and buy price must be positive numbers.");
    onAdd({ id: uid(), kind, key: opt.key, name: opt.label.split(" — ").pop()!.replace(/ \(\d+\)$/, ""), qty: q, cost: c });
    setPick(""); setQty(""); setCost(""); setErr("");
  };

  return (
    <>
      <h2 className="mt-8 text-lg font-semibold">Holdings</h2>
      <div className="card mt-3 p-4">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <div role="group" aria-label="Type" className="flex gap-1">
            {([["stock", "Stock"], ["mf", "Index fund"]] as const).map(([k, l]) => (
              <button key={k} onClick={() => { setKind(k); setPick(""); }} aria-pressed={kind === k}
                className="rounded-lg border border-[var(--border)] px-3 py-1.5 aria-pressed:bg-[var(--text-primary)] aria-pressed:text-[var(--surface)]">{l}</button>
            ))}
          </div>
          <div className="min-w-56 flex-1">
            <label htmlFor="pick" className="text-[var(--text-secondary)]">{kind === "stock" ? "Stock (Nifty 100)" : "Index fund"}</label>
            <input id="pick" list="pick-list" value={pick} onChange={(e) => setPick(e.target.value)}
              placeholder={kind === "stock" ? "e.g. ICICIBANK" : "e.g. UTI Nifty 50"} className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-1.5" />
            <datalist id="pick-list">{options.map((o) => <option key={o.key} value={o.label} />)}</datalist>
          </div>
          <div>
            <label htmlFor="qty" className="text-[var(--text-secondary)]">{kind === "stock" ? "Shares" : "Units"}</label>
            <input id="qty" type="number" min="0" step="any" value={qty} onChange={(e) => setQty(e.target.value)} className="mt-1 w-28 rounded-lg border border-[var(--border)] bg-transparent px-3 py-1.5" />
          </div>
          <div>
            <label htmlFor="cost" className="text-[var(--text-secondary)]">Avg buy price ₹</label>
            <input id="cost" type="number" min="0" step="any" value={cost} onChange={(e) => setCost(e.target.value)} className="mt-1 w-32 rounded-lg border border-[var(--border)] bg-transparent px-3 py-1.5" />
          </div>
          <button onClick={add} className="rounded-lg bg-[var(--text-primary)] px-4 py-1.5 text-[var(--surface)]">Add</button>
        </div>
        {err && <p role="alert" className="mt-2 text-sm" style={{ color: "var(--critical)" }}>{err}</p>}
      </div>

      {rows.length > 0 ? (
        <div className="card mt-3 overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <caption className="sr-only">Your holdings with current value and profit or loss</caption>
            <thead><tr className="text-left text-[var(--text-secondary)]">
              <th className="p-3">Holding</th><th className="p-3">Qty</th><th className="p-3">Buy ₹</th><th className="p-3">Now ₹</th>
              <th className="p-3">Put in</th><th className="p-3">Worth</th><th className="p-3">P/L</th><th className="p-3">Flags</th><th className="p-3"><span className="sr-only">Remove</span></th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.h.id} className="border-t border-[var(--border)]">
                  <td className="p-3"><div className="font-medium">{r.h.kind === "stock" ? r.h.key : r.h.name}</div>
                    <div className="text-xs text-[var(--text-secondary)]">{r.h.kind === "stock" ? r.h.name : `Index fund · ${r.h.key}`}</div></td>
                  <td className="p-3 tabular-nums">{r.h.qty}</td>
                  <td className="p-3 tabular-nums">{r.h.cost.toLocaleString("en-IN")}</td>
                  <td className="p-3 tabular-nums">{r.price != null ? r.price.toLocaleString("en-IN") : "no data"}</td>
                  <td className="p-3 tabular-nums">{inr(r.invested)}</td>
                  <td className="p-3 tabular-nums">{r.value != null ? inr(r.value) : "—"}</td>
                  <td className="p-3 tabular-nums" style={{ color: r.pl != null ? tone(r.pl) : undefined }}>
                    {r.pl != null ? `${signedInr(r.pl)} (${pctf(r.plPct!)})` : "—"}</td>
                  <td className="p-3 text-xs">
                    {r.onSale && <span className="mr-2" title={`${Math.abs(r.drawdown ?? 0).toFixed(0)}% below its 52-week high`}>📉 {Math.abs(r.drawdown ?? 0).toFixed(0)}% off high</span>}
                    {r.results && <span title="Board meeting for results — the price often moves sharply around this date">📅 results {fmtFull(r.results)}</span>}
                  </td>
                  <td className="p-3"><button onClick={() => onRemove(r.h.id)} aria-label={`Remove ${r.h.key}`} className="rounded-lg border border-[var(--border)] px-2 py-1 text-xs">✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">Nothing here yet. Add what you hold — stocks from the Nifty 100 and index funds are supported, because those are the ones with daily data in this app.</p>
      )}
    </>
  );
}

function FundSection({ entries, balance, planner, onAdd, onRemove }: {
  entries: FundEntry[]; balance: number; planner: PlannerData | null;
  onAdd: (e: FundEntry) => void; onRemove: (id: string) => void;
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const a = planner?.advice;
  const log = useMemo(() => [...entries].sort((x, y) => y.date.localeCompare(x.date)).slice(0, 8), [entries]);

  const add = (sign: 1 | -1) => {
    const v = Number(amount);
    if (!(v > 0)) return;
    onAdd({ id: uid(), date: today(), amount: sign * v, note: note.trim() || (sign > 0 ? "added to fund" : "extra buy") });
    setAmount(""); setNote("");
  };

  return (
    <>
      <h2 className="mt-8 text-lg font-semibold">Opportunity fund</h2>
      <p className="text-sm text-[var(--text-secondary)]">The cash you keep aside for extra buys. Add to it monthly; log what you invest so the balance stays honest.</p>
      <div className="card mt-3 grid gap-6 p-5 sm:grid-cols-2">
        <div>
          <div className="text-sm text-[var(--text-secondary)]">Balance</div>
          <div className="mt-1 text-3xl font-semibold tabular-nums" style={{ color: balance < 0 ? "var(--critical)" : undefined }}>{inr(balance)}</div>
          {balance < 0 && <p className="mt-1 text-sm" style={{ color: "var(--critical)" }}>You logged more buys than money added — fix the log.</p>}
          <div className="mt-4 flex flex-wrap items-end gap-2 text-sm">
            <div>
              <label htmlFor="famt" className="text-[var(--text-secondary)]">Amount ₹</label>
              <input id="famt" type="number" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} className="mt-1 w-28 rounded-lg border border-[var(--border)] bg-transparent px-3 py-1.5" />
            </div>
            <div className="flex-1">
              <label htmlFor="fnote" className="text-[var(--text-secondary)]">Note</label>
              <input id="fnote" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-1.5" />
            </div>
            <button onClick={() => add(1)} className="rounded-lg border border-[var(--border)] px-3 py-1.5">+ Add money</button>
            <button onClick={() => add(-1)} className="rounded-lg border border-[var(--border)] px-3 py-1.5">− Log a buy</button>
          </div>
          {log.length > 0 && (
            <ul className="mt-4 space-y-1 text-sm">
              {log.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-2">
                  <span className="text-[var(--text-secondary)]">{fmtFull(e.date)} · {e.note}</span>
                  <span className="flex items-center gap-2">
                    <span className="tabular-nums" style={{ color: tone(e.amount) }}>{signedInr(e.amount)}</span>
                    <button onClick={() => onRemove(e.id)} aria-label="Remove entry" className="text-xs text-[var(--text-muted)]">✕</button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-sm text-[var(--text-secondary)]">What the rule says now</div>
          {a ? (
            <>
              <p className="mt-1 text-[15px]">
                {a.extra_amount > 0
                  ? <>Deploy <strong>{inr(Math.min(a.extra_amount, Math.max(balance, 0)))}</strong> this month{balance < a.extra_amount ? <> (rule says {inr(a.extra_amount)}, your fund has {inr(Math.max(balance, 0))})</> : null}. {a.zone} zone{a.drawdown <= -10 ? ", and the market is well off its high" : ""}.</>
                  : <>Hold. No extra-buy signal — let the fund grow for the next dip.</>}
              </p>
              <ul className="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
                {a.dip_levels.map((l) => {
                  const hit = a.drawdown <= l.drawdown;
                  return <li key={l.drawdown}>{hit ? "✅" : "○"} Nifty {Math.abs(l.drawdown)}% below its high (≈{l.nifty_level.toLocaleString("en-IN")}) {hit ? "— hit" : "— not yet"}</li>;
                })}
                <li>Nifty now: {a.nifty.toLocaleString("en-IN")} ({a.drawdown.toFixed(1)}% from the high). Data {fmtFull(a.date)}.</li>
              </ul>
            </>
          ) : <p className="mt-1 text-sm text-[var(--text-secondary)]">Planner data not loaded yet.</p>}
        </div>
      </div>
    </>
  );
}

function EarningsSection({ earnings, held }: { earnings: EarningsData | null; held: Set<string> }) {
  if (!earnings || earnings.count === 0) return null;
  return (
    <>
      <h2 className="mt-8 text-lg font-semibold">Results calendar</h2>
      <p className="text-sm text-[var(--text-secondary)]">Upcoming board meetings for results in the Nifty 100 (next {earnings.horizon_days} days). Prices often move sharply on results day. ★ marks stocks you hold.</p>
      <div className="card mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <caption className="sr-only">Upcoming results dates</caption>
          <thead><tr className="text-left text-[var(--text-secondary)]"><th className="p-3">Date</th><th className="p-3">Stock</th><th className="p-3">Purpose</th></tr></thead>
          <tbody>
            {earnings.items.map((e, i) => (
              <tr key={i} className="border-t border-[var(--border)]" style={held.has(e.symbol) ? { background: "var(--grid)" } : undefined}>
                <td className="p-3 whitespace-nowrap tabular-nums">{fmtFull(e.date)}</td>
                <td className="p-3"><span className="font-medium">{held.has(e.symbol) ? "★ " : ""}{e.symbol}</span> <span className="text-xs text-[var(--text-secondary)]">{e.company}</span></td>
                <td className="p-3 text-[var(--text-secondary)]">{e.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function BackupSection({ saved, onImport }: { saved: Saved; onImport: (s: Saved) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState("");

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(saved, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `pe-tracker-portfolio-${today()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const importJson = (f: File) => {
    f.text().then((t) => {
      const p = JSON.parse(t);
      if (!Array.isArray(p.holdings) || !Array.isArray(p.fund)) throw new Error("wrong shape");
      onImport({ holdings: p.holdings, fund: p.fund });
      setMsg(`Imported ${p.holdings.length} holdings and ${p.fund.length} fund entries.`);
    }).catch(() => setMsg("That file is not a backup from this page."));
  };

  return (
    <div className="mt-8 flex flex-wrap items-center gap-2 text-sm">
      <button onClick={exportJson} className="rounded-lg border border-[var(--border)] px-3 py-1.5">Export backup</button>
      <button onClick={() => fileRef.current?.click()} className="rounded-lg border border-[var(--border)] px-3 py-1.5">Import backup</button>
      <input ref={fileRef} type="file" accept="application/json" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) importJson(f); e.target.value = ""; }} />
      {msg && <span role="status" className="text-[var(--text-secondary)]">{msg}</span>}
    </div>
  );
}
