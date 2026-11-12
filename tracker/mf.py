"""Index-fund NAVs from AMFI's official daily list (NAVAll.txt).

Only index funds are stored (the planner is about index investing). The whole-market file is ~18k schemes;
index funds are a few hundred, so the committed JSON stays small. Browsers cannot call mfapi.in directly
(no CORS), which is why the workflow snapshots NAVs into the repo instead.
"""
from __future__ import annotations

from pathlib import Path

import requests

from . import store

NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
HEADERS = {"User-Agent": "Mozilla/5.0 (pe-tracker)"}
TIMEOUT = 60
MIN_SCHEMES = 100  # sanity floor; AMFI lists several hundred index funds

MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


class MFError(RuntimeError):
    pass


def _iso(d: str) -> str:
    """'09-Nov-2026' -> '2026-11-09' (AMFI's date format)."""
    dd, mon, yy = d.strip().split("-")
    return f"{yy}-{MONTHS[mon[:3].title()]:02d}-{int(dd):02d}"


def parse_navall(text: str) -> list[dict]:
    """AMFI NAVAll.txt -> index-fund schemes [{code, name, category, nav, date}]."""
    category = None
    out = []
    for line in text.lstrip("﻿").splitlines():
        line = line.strip()
        if not line:
            continue
        if ";" not in line:
            # Either a scheme-type header like "Open Ended Schemes(Index Funds - Equity Funds)"
            # or a fund-house name. Only the former changes the category.
            if "scheme" in line.lower() and "(" in line:
                category = line
            continue
        f = line.split(";")
        if len(f) < 6 or not f[0].strip().isdigit():
            continue  # column header or malformed row
        if not category or "index fund" not in category.lower():
            continue
        # Two known layouts: 6 cols (code;isin;isin;name;nav;date) and 8 cols (…;name;plan;option;nav;date)
        name, nav_s, date_s = f[3].strip(), f[-2].strip(), f[-1].strip()
        try:
            nav = float(nav_s)
            date = _iso(date_s)
        except (ValueError, KeyError):
            continue  # "N.A." NAVs and similar
        out.append({"code": f[0].strip(), "name": name, "category": category, "nav": nav, "date": date})
    return out


def refresh(data_dir: Path | None = None, session: requests.Session | None = None) -> dict:
    s = session or requests.Session()
    r = s.get(NAVALL_URL, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        raise MFError(f"AMFI NAVAll: HTTP {r.status_code}")
    schemes = parse_navall(r.text)
    if len(schemes) < MIN_SCHEMES:
        raise MFError(f"AMFI NAVAll: only {len(schemes)} index funds parsed, format may have changed")
    payload = {"date": max(x["date"] for x in schemes), "count": len(schemes), "schemes": schemes}
    store.write_json("mf.json", payload, data_dir)
    return payload
