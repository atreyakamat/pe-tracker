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

    def to_dict(self) -> dict:
        return asdict(self)


def percentile_rank(values: list[float], x: float) -> float:
    """Share (0-100) of values less than or equal to x."""
    if not values:
        raise ValueError("no values")
    return 100.0 * sum(1 for v in values if v <= x) / len(values)


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
    )
