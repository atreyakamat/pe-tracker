"""Fetch Nifty 50 valuation data (PE / PB / dividend yield).

Primary: niftyindices.com historical PE/PB/DivYield endpoint (full history).
Fallback: NSE allIndices endpoint (today's value only).

Neither is an official public API, so every fetch is defensive and the caller
must treat a failure as "alert me", never as "no signal".
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import requests

INDEX_NAME = "NIFTY 50"
NIFTYINDICES_URL = "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricalDataDBtoJSON"
NSE_HOME = "https://www.nseindia.com"
NSE_ALL_INDICES = "https://www.nseindia.com/api/allIndices"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 30
# niftyindices rejects very long ranges, so request in chunks.
CHUNK_DAYS = 365 * 2


class FetchError(RuntimeError):
    pass


def _to_float(value: Any) -> float | None:
    try:
        f = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _parse_date(value: str) -> str:
    """niftyindices returns e.g. '07 Nov 2025'; normalise to ISO."""
    value = value.strip()
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise FetchError(f"Unrecognised date format: {value!r}")


def parse_niftyindices(payload: dict) -> list[dict]:
    """Turn the raw niftyindices response into [{date, pe, pb, div_yield}]."""
    raw = payload.get("d")
    if raw is None:
        raise FetchError("niftyindices response missing 'd' field")
    rows = json.loads(raw) if isinstance(raw, str) else raw
    out = []
    for r in rows:
        pe = _to_float(r.get("pe"))
        if pe is None:
            continue  # skip rows with no usable PE
        out.append(
            {
                "date": _parse_date(r["DATE"]),
                "pe": pe,
                "pb": _to_float(r.get("pb")),
                "div_yield": _to_float(r.get("divYield")),
            }
        )
    return out


def fetch_niftyindices(
    start: date, end: date, index_name: str = INDEX_NAME, session: requests.Session | None = None
) -> list[dict]:
    s = session or requests.Session()
    rows: dict[str, dict] = {}
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        cinfo = {
            "name": index_name,
            "startDate": cursor.strftime("%d-%b-%Y"),
            "endDate": chunk_end.strftime("%d-%b-%Y"),
            "indexName": index_name,
        }
        resp = s.post(
            NIFTYINDICES_URL,
            data=json.dumps({"cinfo": json.dumps(cinfo)}),
            headers={
                **HEADERS,
                "Content-Type": "application/json; charset=UTF-8",
                "Origin": "https://www.niftyindices.com",
                "Referer": "https://www.niftyindices.com/reports/historical-data",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            raise FetchError(f"niftyindices HTTP {resp.status_code}")
        for row in parse_niftyindices(resp.json()):
            rows[row["date"]] = row
        cursor = chunk_end + timedelta(days=1)
    return [rows[k] for k in sorted(rows)]


def parse_nse_all_indices(payload: dict, index_name: str = INDEX_NAME) -> dict:
    for item in payload.get("data", []):
        if item.get("index") == index_name or item.get("indexSymbol") == index_name:
            pe = _to_float(item.get("pe"))
            if pe is None:
                raise FetchError(f"NSE allIndices has no PE for {index_name}")
            return {
                "date": date.today().isoformat(),
                "pe": pe,
                "pb": _to_float(item.get("pb")),
                "div_yield": _to_float(item.get("dy")),
            }
    raise FetchError(f"{index_name} not found in NSE allIndices response")


def fetch_nse_today(index_name: str = INDEX_NAME, session: requests.Session | None = None) -> dict:
    s = session or requests.Session()
    # NSE needs a cookie from the home page first.
    s.get(NSE_HOME, headers=HEADERS, timeout=TIMEOUT)
    resp = s.get(NSE_ALL_INDICES, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise FetchError(f"NSE HTTP {resp.status_code}")
    return parse_nse_all_indices(resp.json(), index_name)


def fetch_latest(index_name: str = INDEX_NAME, days_back: int = 10) -> tuple[list[dict], str]:
    """Latest rows for one index plus the name of the source that worked."""
    errors = []
    try:
        end = date.today()
        rows = fetch_niftyindices(end - timedelta(days=days_back), end, index_name)
        if rows:
            return rows, "niftyindices"
        errors.append("niftyindices returned no rows")
    except Exception as e:  # noqa: BLE001 - we want every failure mode recorded
        errors.append(f"niftyindices: {e}")
    try:
        return [fetch_nse_today(index_name)], "nse"
    except Exception as e:  # noqa: BLE001
        errors.append(f"nse: {e}")
    raise FetchError("; ".join(errors))
