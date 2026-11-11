"""Upcoming board-meeting / results dates for the stock universe, from NSE's event calendar."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import requests

from . import store

EVENTS_URL = "https://www.nseindia.com/api/event-calendar"
WARMUP_URL = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
TIMEOUT = 25
HORIZON_DAYS = 45

MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


class EarningsError(RuntimeError):
    pass


def _iso(d: str) -> str:
    """'12-Nov-2026' -> '2026-11-12'."""
    dd, mon, yy = d.strip().split("-")
    return f"{yy}-{MONTHS[mon[:3].title()]:02d}-{int(dd):02d}"


def parse_events(payload: list, symbols: set[str], today: date) -> list[dict]:
    """Keep events for our universe from yesterday up to HORIZON_DAYS ahead, soonest first."""
    lo = (today - timedelta(days=1)).isoformat()
    hi = (today + timedelta(days=HORIZON_DAYS)).isoformat()
    out = []
    for e in payload:
        sym = (e.get("symbol") or "").strip()
        if sym not in symbols:
            continue
        try:
            d = _iso(e.get("date") or "")
        except (ValueError, KeyError):
            continue
        if not lo <= d <= hi:
            continue
        out.append({"symbol": sym, "company": (e.get("company") or sym).strip(),
                    "purpose": (e.get("purpose") or "").strip() or "Board meeting", "date": d})
    out.sort(key=lambda x: (x["date"], x["symbol"]))
    return out


def fetch_events(session: requests.Session | None = None) -> list:
    s = session or requests.Session()
    try:  # the homepage visit sets cookies; a 403 here is fine as long as the API call works
        s.get(WARMUP_URL, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        pass
    r = s.get(EVENTS_URL, params={"index": "equities"}, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        raise EarningsError(f"event-calendar: HTTP {r.status_code}")
    try:
        payload = r.json()
    except ValueError:
        raise EarningsError("event-calendar: response was not JSON") from None
    if not isinstance(payload, list):
        raise EarningsError(f"event-calendar: unexpected shape {type(payload).__name__}")
    return payload


def refresh(universe: list[dict], data_dir: Path | None = None,
            session: requests.Session | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    events = parse_events(fetch_events(session), {u["symbol"] for u in universe}, today)
    payload = {"date": today.isoformat(), "horizon_days": HORIZON_DAYS, "count": len(events), "items": events}
    store.write_json("earnings.json", payload, data_dir)
    return payload
