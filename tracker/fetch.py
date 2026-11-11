"""Fetch Nifty 50 valuation data (PE / PB / dividend yield).

niftyindices.com historical PE/PB/DivYield endpoint (full history, 1-year requests) is the only
source of stored history. The NSE allIndices endpoint is kept for `probe` diagnostics only.

Neither is an official public API, so every fetch is defensive and the caller
must treat a failure as "alert me", never as "no signal".
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from typing import Any

import requests

INDEX_NAME = "NIFTY 50"
# niftyindices.com rebuilt its site in 2025/26: the old Backpage.aspx endpoints now redirect to a login
# page. This is the endpoint the site's own historical-data page calls today. The path is
# case-sensitive, a wrong one returns an HTML page instead of JSON.
NIFTYINDICES_PAGE = "https://www.niftyindices.com/reports/historical-data"
NIFTYINDICES_URL = "https://www.niftyindices.com/BackPage/getpepbHistoricaldataDBtoString"
NIFTYINDICES_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.niftyindices.com",
    "Referer": NIFTYINDICES_PAGE,
}
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
# The site's own UI refuses ranges over one year, so we request at most that much at a time.
CHUNK_DAYS = 364
REQUEST_PAUSE = 0.3  # seconds between requests, to be polite


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


def parse_niftyindices(payload: Any) -> list[dict]:
    """Turn the raw niftyindices response into [{date, pe, pb, div_yield}].

    Current responses are a bare JSON array. Older ones wrapped a JSON string in {"d": ...};
    both are accepted.
    """
    if isinstance(payload, dict):
        raw = payload.get("d")
        if raw is None:
            raise FetchError("niftyindices response missing 'd' field")
        rows = json.loads(raw) if isinstance(raw, str) else raw
    else:
        rows = payload
    if not isinstance(rows, list):
        raise FetchError(f"Unexpected niftyindices payload type: {type(rows).__name__}")
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
    start: date,
    end: date,
    name: str = INDEX_NAME,
    index_name: str | None = None,
    session: requests.Session | None = None,
) -> list[dict]:
    """History for one index. `name` is niftyindices' trading name, `index_name` its long name."""
    own_session = session is None
    s = session or requests.Session()
    if own_session:
        try:  # pick up any cookies the site sets, as a browser would
            s.get(NIFTYINDICES_PAGE, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=TIMEOUT)
        except requests.RequestException:
            pass
    index_name = index_name or name
    rows: dict[str, dict] = {}
    cursor, first = start, True
    while cursor <= end:
        if not first and REQUEST_PAUSE:
            time.sleep(REQUEST_PAUSE)
        first = False
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        # The server expects a single-quoted pseudo-JSON string inside the JSON body.
        cinfo = (
            f"{{'name':'{name}','startDate':'{cursor.strftime('%d-%b-%Y')}',"
            f"'endDate':'{chunk_end.strftime('%d-%b-%Y')}','indexName':'{index_name}'}}"
        )
        resp = s.post(
            NIFTYINDICES_URL,
            json={"cinfo": cinfo},
            headers={**HEADERS, **NIFTYINDICES_HEADERS},
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        if resp.status_code != 200:
            raise FetchError(f"niftyindices HTTP {resp.status_code}: {resp.text[:120]!r}")
        try:
            payload = resp.json()
        except ValueError:
            raise FetchError(
                f"niftyindices returned non-JSON (HTTP {resp.status_code}, "
                f"{resp.headers.get('Content-Type', '?')}): {resp.text[:150]!r}"
            ) from None
        for row in parse_niftyindices(payload):
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


def fetch_latest(index, days_back: int = 10) -> tuple[list[dict], str]:
    """Latest rows for one tracker.indices.Index, from niftyindices only.

    NSE's allIndices endpoint is deliberately NOT used as a fallback for stored history: during
    market hours it reports the previous day's PE under today's date, which would silently
    mislabel the data. A failure here is reported loudly instead (see run.cmd_daily).
    """
    try:
        end = date.today()
        rows = fetch_niftyindices(end - timedelta(days=days_back), end, index.ni_trading, index.ni_index_name)
    except Exception as e:  # noqa: BLE001 - we want every failure mode recorded
        raise FetchError(f"niftyindices: {e}") from e
    if not rows:
        raise FetchError(f"niftyindices returned no rows for {index.ni_trading!r} in the last {days_back} days")
    return rows, "niftyindices"
