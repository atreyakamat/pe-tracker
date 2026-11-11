"""SIP planner and backtest for Nifty 50.

Strategies, simulated month by month with only data available on that day (trailing 10y PE window, outlier
days excluded, so no look-ahead):
  plain      : SIP_AMOUNT every month, never changed.
  scaled     : TESTED AND REJECTED. Cuts the SIP to 0.5x when expensive and doubles it when cheap, funded from
               the same budget. It lagged plain SIP, because expensive months did not underperform.
  core_plus  : the plain SIP, always, plus EXTRA money (a separate opportunity fund) when the PE zone is BUY
               and/or Nifty is well below its 52-week high.
The core_plus rule was picked after looking at forward returns on this same history, so its backtest is
in-sample and flatters it. One bull-market regime, about 10 years. Signal only, not financial advice.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import requests

from . import stocks, store

from .signal import BUY_PCT, EXPENSIVE_PCT, LOOKBACK_YEARS, split_outliers

SIP_AMOUNT = 12_000
SCALED = {"BUY": 2.0, "NEUTRAL": 1.0, "EXPENSIVE": 0.5}   # the rejected experiment
ZONE_EXTRA = {"BUY": 1.0, "NEUTRAL": 0.0, "EXPENSIVE": 0.0}  # extra multiple of the SIP in the opportunity fund
DIP_EXTRA = [(-20.0, 1.0), (-10.0, 0.5)]   # (drawdown % at or below, extra multiple of the SIP amount)
MAX_EXTRA = 2.0                            # cap on total extra, in multiples of the SIP
MIN_HISTORY = 500                           # trailing PE days needed before a zone is trusted
DD_WINDOW = 252


def pe_zone(pe_rows: list[dict], on: str) -> tuple[str, float] | None:
    """(zone, percentile) for `on`, using only PE rows up to that date. None if too little history."""
    cutoff = (date.fromisoformat(on) - timedelta(days=365 * LOOKBACK_YEARS)).isoformat()
    win = [r["pe"] for r in pe_rows if cutoff <= r["date"] <= on]
    if len(win) < MIN_HISTORY:
        return None
    today = next(r["pe"] for r in reversed(pe_rows) if r["date"] <= on)
    vals, cap = split_outliers(win)
    if today > cap:
        pct = 100.0
    else:
        pct = 100 * sum(1 for v in vals if v <= today) / len(vals)
    zone = "BUY" if pct <= BUY_PCT else "EXPENSIVE" if pct >= EXPENSIVE_PCT else "NEUTRAL"
    return zone, pct


def drawdown(closes: list[float]) -> float:
    """% below the trailing 52-week high (<= 0)."""
    win = closes[-DD_WINDOW:]
    return (closes[-1] / max(win) - 1) * 100


def dip_extra(dd: float) -> float:
    for level, extra in DIP_EXTRA:
        if dd <= level:
            return extra
    return 0.0


def extra_multiple(zone: str, dd: float) -> float:
    """Extra money (in multiples of the SIP) the rule adds this month, capped."""
    return min(MAX_EXTRA, ZONE_EXTRA[zone] + dip_extra(dd))


def xirr(flows: list[tuple[str, float]]) -> float | None:
    """Annualised money-weighted return of dated cash flows (negative = money in). None if undefined."""
    if not flows or not any(a > 0 for _, a in flows) or not any(a < 0 for _, a in flows):
        return None
    d0 = date.fromisoformat(flows[0][0])
    t = [(date.fromisoformat(d) - d0).days / 365 for d, _ in flows]

    def npv(r):
        return sum(a / (1 + r) ** ti for (_, a), ti in zip(flows, t))

    lo, hi = -0.9, 5.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def month_starts(dates: list[str]) -> list[str]:
    """First available trading date of each calendar month."""
    seen, out = set(), []
    for d in dates:
        ym = d[:7]
        if ym not in seen:
            seen.add(ym)
            out.append(d)
    return out


def backtest(pe_rows: list[dict], price_rows: list[dict], sip: float = SIP_AMOUNT) -> dict:
    """Monthly SIP simulation. Returns summary per strategy and a month-by-month value series."""
    price = {r["date"]: r["close"] for r in price_rows}
    pe_dates = {r["date"] for r in pe_rows}
    common = sorted(d for d in price if d in pe_dates)
    months = []
    for d in month_starts(common):
        z = pe_zone(pe_rows, d)
        if z is not None:
            months.append((d, z))
    if len(months) < 12:
        raise ValueError("not enough history to backtest")

    closes_sorted = [(r["date"], r["close"]) for r in price_rows]
    keys = ("plain", "scaled", "core_plus")
    st = {k: {"units": 0.0, "pool": 0.0, "paid": 0.0} for k in keys}
    flows = {k: [] for k in keys}
    extra_units, extra_paid, extra_flows = 0.0, 0.0, []
    series = []
    for d, (zone, _pct) in months:
        px = price[d]
        dd_pct = drawdown([c for dd, c in closes_sorted if dd <= d])
        for k, a in st.items():
            a["pool"] += sip
            a["paid"] += sip
            flows[k].append((d, -sip))
            spend = sip if k != "scaled" else min(a["pool"], sip * SCALED[zone])
            a["pool"] -= spend
            a["units"] += spend / px
        extra = extra_multiple(zone, dd_pct) * sip
        if extra:
            st["core_plus"]["units"] += extra / px
            st["core_plus"]["paid"] += extra
            flows["core_plus"].append((d, -extra))
            extra_units += extra / px
            extra_paid += extra
            extra_flows.append((d, -extra))
        series.append({"date": d, "paid": st["plain"]["paid"], "paid_plus": st["core_plus"]["paid"],
                       **{k: round(a["units"] * px + a["pool"], 0) for k, a in st.items()}})

    last_d = months[-1][0]
    last_px = price[last_d]
    summary = {}
    for k, a in st.items():
        value = a["units"] * last_px + a["pool"]
        r = xirr(flows[k] + [(last_d, value)])
        summary[k] = {"paid": round(a["paid"]), "value": round(value), "multiple": round(value / a["paid"], 3),
                      "xirr": None if r is None else round(r * 100, 2), "cash_left": round(a["pool"])}
    ex_value = extra_units * last_px
    ex_r = xirr(extra_flows + [(last_d, ex_value)]) if extra_flows else None
    extra_part = {"paid": round(extra_paid), "value": round(ex_value), "buys": len(extra_flows),
                  "xirr": None if ex_r is None else round(ex_r * 100, 2)}
    return {"from": months[0][0], "to": last_d, "months": len(months), "sip": sip, "summary": summary, "extra": extra_part, "series": series}


def advice(pe_rows: list[dict], price_rows: list[dict], sip: float = SIP_AMOUNT) -> dict:
    """What the rule says to do this month, with the Nifty levels where the extra-buy tiers start."""
    on = pe_rows[-1]["date"]
    z = pe_zone(pe_rows, on)
    if z is None:
        raise ValueError("not enough PE history")
    zone, pct = z
    closes = [r["close"] for r in price_rows]
    dd = drawdown(closes)
    high = max(closes[-DD_WINDOW:])
    extra = extra_multiple(zone, dd)
    return {
        "date": on, "sip": sip, "zone": zone, "pe_percentile": round(pct, 1),
        "base_amount": round(sip),
        "drawdown": round(dd, 2), "extra_multiple": extra, "extra_amount": round(sip * extra),
        "total_amount": round(sip * (1 + extra)),
        "nifty": round(closes[-1], 1), "high_52w": round(high, 1),
        "zone_extra": round(sip * ZONE_EXTRA["BUY"]),
        "dip_levels": [{"drawdown": lvl, "extra": round(sip * ex), "nifty_level": round(high * (1 + lvl / 100), 0)} for lvl, ex in sorted(DIP_EXTRA)],
        "max_extra": round(sip * MAX_EXTRA),
        "note": "The SIP never changes. Extra amounts come from a separate opportunity fund. Do not borrow to invest.",
    }


def fetch_nifty_prices(years: int = 12, session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(stocks.CHART_URL.format(sym="%5ENSEI"), params={"range": f"{years}y", "interval": "1d"},
              headers=stocks.HEADERS, timeout=stocks.TIMEOUT)
    if r.status_code != 200:
        raise stocks.StockFetchError(f"Nifty 50 price: HTTP {r.status_code}")
    rows = stocks.parse_chart(r.json())
    if len(rows) < 1000:
        raise stocks.StockFetchError(f"Nifty 50 price: only {len(rows)} rows")
    return rows


def refresh(data_dir: Path | None = None, session: requests.Session | None = None) -> dict:
    """Backtest + this month's advice -> data/planner.json."""
    pe = store.load_history("nifty50", data_dir)
    px = fetch_nifty_prices(session=session)
    payload = {"advice": advice(pe, px), "backtest": backtest(pe, px)}
    store.write_json("planner.json", payload, data_dir)
    return payload
