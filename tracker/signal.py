"""Valuation signal: where is today's PE relative to its own history?"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import mean, median, pstdev

# Zones are based on the percentile of today's PE within the lookback window.
BUY_PCT = 25.0        # at or below -> BUY zone (cheap vs history)
EXPENSIVE_PCT = 75.0  # at or above -> EXPENSIVE zone
LOOKBACK_YEARS = 10
MIN_POINTS = 250      # ~1 year of trading days; below this the signal is unreliable


@dataclass
class Signal:
    date: str
    pe: float
    zone: str            # "BUY" | "NEUTRAL" | "EXPENSIVE"
    percentile: float    # 0-100, share of history at or below today's PE
    median: float
    mean: float
    z_score: float
    min: float
    max: float
    n_points: int
    lookback_years: int
    pb: float | None = None
    div_yield: float | None = None
    pb_percentile: float | None = None
    dy_percentile: float | None = None   # percentile of dividend yield (high yield = cheap)
    composite: float | None = None       # 0-100 "richness": mean of PE pct, PB pct, 100 - yield pct

    def to_dict(self) -> dict:
        return asdict(self)


def percentile_rank(values: list[float], x: float) -> float:
    """Share (0-100) of values less than or equal to x."""
    if not values:
        raise ValueError("no values")
    return 100.0 * sum(1 for v in values if v <= x) / len(values)


def _metric_pct(win: list[dict], field: str) -> float | None:
    """Percentile of today's value of `field` within the window; None if today's value is missing."""
    today_v = win[-1].get(field)
    vals = [r[field] for r in win if r.get(field) is not None]
    if today_v is None or len(vals) < MIN_POINTS:
        return None
    return percentile_rank(vals, today_v)


def window(rows: list[dict], years: int = LOOKBACK_YEARS) -> list[dict]:
    if not rows:
        return []
    last = date.fromisoformat(rows[-1]["date"])
    cutoff = (last - timedelta(days=365 * years)).isoformat()
    return [r for r in rows if r["date"] >= cutoff]


def classify(pct: float, buy_pct: float = BUY_PCT, exp_pct: float = EXPENSIVE_PCT) -> str:
    if pct <= buy_pct:
        return "BUY"
    if pct >= exp_pct:
        return "EXPENSIVE"
    return "NEUTRAL"


def compute_signal(rows: list[dict], years: int = LOOKBACK_YEARS) -> Signal:
    """rows must be date-sorted. Uses the latest row as 'today'."""
    win = window(rows, years)
    if len(win) < MIN_POINTS:
        raise ValueError(
            f"Only {len(win)} data points in window; need at least {MIN_POINTS}. Backfill more history."
        )
    pes = [r["pe"] for r in win]
    today = win[-1]
    sd = pstdev(pes)
    z = (today["pe"] - mean(pes)) / sd if sd else 0.0
    pct = percentile_rank(pes, today["pe"])
    pb_pct = _metric_pct(win, "pb")
    dy_pct = _metric_pct(win, "div_yield")
    parts = [pct] + ([pb_pct] if pb_pct is not None else []) + ([100 - dy_pct] if dy_pct is not None else [])
    return Signal(
        date=today["date"],
        pe=today["pe"],
        zone=classify(pct),
        percentile=round(pct, 1),
        median=round(median(pes), 2),
        mean=round(mean(pes), 2),
        z_score=round(z, 2),
        min=min(pes),
        max=max(pes),
        n_points=len(pes),
        lookback_years=years,
        pb=today.get("pb"),
        div_yield=today.get("div_yield"),
        pb_percentile=None if pb_pct is None else round(pb_pct, 1),
        dy_percentile=None if dy_pct is None else round(dy_pct, 1),
        composite=round(sum(parts) / len(parts), 1),
    )
