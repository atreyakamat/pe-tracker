"""Cross-index comparison and rule-based inference.

Everything here is descriptive statistics on valuation history. It says where an index sits vs
its own past and vs other indices. It does not predict prices.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import sqrt
from statistics import median

from .indices import BY_KEY, PAIRS
from .signal import LOOKBACK_YEARS, MIN_POINTS, Signal, percentile_rank

CORR_YEARS = 3


def _cutoff(rows: list[dict], years: int) -> str:
    last = date.fromisoformat(rows[-1]["date"])
    return (last - timedelta(days=365 * years)).isoformat()


def relative_series(rows_a: list[dict], rows_b: list[dict], years: int = LOOKBACK_YEARS) -> list[dict]:
    """Premium of A's PE over B's PE (%), on dates both have."""
    if not rows_a or not rows_b:
        return []
    b_by_date = {r["date"]: r["pe"] for r in rows_b}
    cut = _cutoff(rows_a, years)
    return [
        {"date": r["date"], "premium": (r["pe"] / b_by_date[r["date"]] - 1) * 100}
        for r in rows_a
        if r["date"] >= cut and r["date"] in b_by_date
    ]


def relative_stats(rows_a: list[dict], rows_b: list[dict]) -> dict | None:
    series = relative_series(rows_a, rows_b)
    if len(series) < MIN_POINTS:
        return None
    vals = [s["premium"] for s in series]
    today = vals[-1]
    return {
        "date": series[-1]["date"],
        "premium": round(today, 1),
        "median": round(median(vals), 1),
        "percentile": round(percentile_rank(vals, today), 1),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
    }


def _pct_changes(rows: list[dict], cut: str) -> dict[str, float]:
    out, prev = {}, None
    for r in rows:
        if r["date"] < cut:
            prev = r["pe"]
            continue
        if prev:
            out[r["date"]] = r["pe"] / prev - 1
        prev = r["pe"]
    return out


def _pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 30:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sqrt(sxx * syy)


def correlation(histories: dict[str, list[dict]], years: int = CORR_YEARS) -> dict:
    """Pearson correlation of daily PE % changes over the last `years` years."""
    keys = [k for k, rows in histories.items() if len(rows) > MIN_POINTS]
    changes = {}
    for k in keys:
        rows = histories[k]
        changes[k] = _pct_changes(rows, _cutoff(rows, years))
    matrix = []
    for a in keys:
        row = []
        for b in keys:
            if a == b:
                row.append(1.0)
                continue
            common = sorted(set(changes[a]) & set(changes[b]))
            c = _pearson([changes[a][d] for d in common], [changes[b][d] for d in common])
            row.append(None if c is None else round(c, 2))
        matrix.append(row)
    return {"keys": keys, "matrix": matrix, "years": years}


def build_table(signals: dict[str, Signal]) -> list[dict]:
    """Ranked cheapest to richest by composite (mean of PE, PB and yield percentiles)."""
    rows = []
    for key, sig in signals.items():
        idx = BY_KEY[key]
        rows.append(
            {
                "key": key,
                "label": idx.label,
                "group": idx.group,
                "pe": sig.pe,
                "zone": sig.zone,
                "pe_percentile": sig.percentile,
                "pb": sig.pb,
                "pb_percentile": sig.pb_percentile,
                "div_yield": sig.div_yield,
                "dy_percentile": sig.dy_percentile,
                "composite": sig.composite,
                "median_pe": sig.median,
            }
        )
    rows.sort(key=lambda r: (r["composite"] if r["composite"] is not None else 101))
    return rows


def _label(key: str) -> str:
    return BY_KEY[key].label


def make_insights(table: list[dict], relatives: list[dict], corr: dict) -> list[str]:
    out: list[str] = []
    if not table:
        return out

    cheapest, richest = table[0], table[-1]
    if len(table) > 1:
        out.append(
            f"Cheapest vs its own history: {cheapest['label']} (valuation score {cheapest['composite']:.0f}/100, "
            f"PE {cheapest['pe']:.1f}). Richest: {richest['label']} (score {richest['composite']:.0f}, PE {richest['pe']:.1f})."
        )
        spread = richest["composite"] - cheapest["composite"]
        if spread >= 40:
            out.append("Valuations are uneven: some segments are far cheaper than others relative to their own history.")

    buys = [r["label"] for r in table if r["zone"] == "BUY"]
    rich = [r["label"] for r in table if r["zone"] == "EXPENSIVE"]
    if buys:
        out.append(f"In BUY zone ({len(buys)} of {len(table)}): {', '.join(buys)}.")
    else:
        out.append(f"No index is in its BUY zone today ({len(table)} tracked).")
    if rich:
        out.append(f"Expensive vs history: {', '.join(rich)}.")

    for rel in relatives:
        a, b = _label(rel["a"]), _label(rel["b"])
        pct, prem = rel["percentile"], rel["premium"]
        side = "premium" if prem >= 0 else "discount"
        line = (
            f"{a} trades at a {abs(prem):.0f}% {side} to {b}. Its PE relative to {b} is lower than on "
            f"{100 - pct:.0f}% of days in the last {LOOKBACK_YEARS}y."
        )
        if pct <= 25:
            line += f" That gap is unusually low, so {a} looks cheap relative to {b}."
        elif pct >= 75:
            line += f" That gap is unusually high, so {a} looks rich relative to {b}."
        out.append(line)

    keys, m = corr["keys"], corr["matrix"]
    if len(keys) >= 3:
        avg = {}
        for i, k in enumerate(keys):
            vals = [v for j, v in enumerate(m[i]) if j != i and v is not None]
            if vals:
                avg[k] = sum(vals) / len(vals)
        if avg:
            lo = min(avg, key=avg.get)
            out.append(
                f"{_label(lo)} moves least in step with the others (average correlation {avg[lo]:.2f} "
                f"over {corr['years']}y), so it diversifies valuation risk the most."
            )
    return out


def build_compare(histories: dict[str, list[dict]], signals: dict[str, Signal]) -> dict:
    table = build_table(signals)
    relatives = []
    for a, b in PAIRS:
        if a in histories and b in histories:
            st = relative_stats(histories[a], histories[b])
            if st:
                relatives.append({"a": a, "b": b, **st})
    corr = correlation(histories)
    date_ = max((s.date for s in signals.values()), default=None)
    return {
        "date": date_,
        "table": table,
        "relative": relatives,
        "correlation": corr,
        "insights": make_insights(table, relatives, corr),
    }
