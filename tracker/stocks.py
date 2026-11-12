"""Hot-stocks ranking for the Nifty 100 universe (which contains the Sensex 30 large caps).

Data: constituents from niftyindices.com, daily price + volume from Yahoo Finance's chart endpoint.
There is no free per-stock PE history, so "hot" is price/volume momentum only. It says what the market is
buying, not what is cheap. Signal only, not financial advice.
"""
from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from . import store

UNIVERSE_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
HEADERS = {"User-Agent": "Mozilla/5.0 (pe-tracker)"}
TIMEOUT = 25
PAUSE = 0.25

# Trading-day lookbacks
D1M, D3M, D6M, D12M, D52W, DMA = 21, 63, 126, 252, 252, 200

# Hot score weights (sum to 1). Each factor is turned into a 0-100 rank across the universe.
WEIGHTS = {"ret_1m": 0.20, "ret_3m": 0.30, "ret_6m": 0.15, "vol_surge": 0.15, "near_high": 0.20}
DIP_DRAWDOWN = 15.0   # % below 52-week high to count as "on sale"
MAX_FAIL_SHARE = 0.2  # fail the run if more than this share of stocks can't be fetched


class StockFetchError(RuntimeError):
    pass


def yahoo_symbol(nse_symbol: str) -> str:
    return quote(nse_symbol, safe="") + ".NS"


def parse_universe(text: str) -> list[dict]:
    rows = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    out = []
    for r in rows:
        sym = (r.get("Symbol") or "").strip()
        if sym:
            out.append({"symbol": sym, "name": (r.get("Company Name") or sym).strip(), "industry": (r.get("Industry") or "").strip()})
    return out


def fetch_universe(session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(UNIVERSE_URL, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        raise StockFetchError(f"universe: HTTP {r.status_code}")
    uni = parse_universe(r.text)
    if len(uni) < 90:
        raise StockFetchError(f"universe: only {len(uni)} symbols parsed")
    return uni


def parse_chart(payload: dict) -> list[dict]:
    """Yahoo chart JSON -> [{date, close, volume}] oldest first, skipping empty days."""
    res = (payload.get("chart") or {}).get("result")
    if not res:
        err = (payload.get("chart") or {}).get("error")
        raise StockFetchError(f"no chart result: {err}")
    res = res[0]
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    adj = (((res.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose")
    closes = adj or q.get("close") or []
    vols = q.get("volume") or [None] * len(ts)
    out = []
    for t, c, v in zip(ts, closes, vols):
        if c is None:
            continue
        d = datetime.fromtimestamp(t + 19800, tz=timezone.utc).date().isoformat()  # IST
        out.append({"date": d, "close": float(c), "volume": float(v or 0)})
    # a partial/live last bar can duplicate a date; keep the last one
    by = {r["date"]: r for r in out}
    return [by[k] for k in sorted(by)]


def fetch_prices(symbol: str, range_: str = "2y", session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(CHART_URL.format(sym=yahoo_symbol(symbol)), params={"range": range_, "interval": "1d"}, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        raise StockFetchError(f"{symbol}: HTTP {r.status_code}")
    try:
        payload = r.json()
    except ValueError:
        raise StockFetchError(f"{symbol}: response was not JSON") from None
    return parse_chart(payload)


def _ret(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return None
    return (closes[-1] / closes[-n - 1] - 1) * 100


def compute_metrics(rows: list[dict]) -> dict | None:
    """Per-stock signals from daily rows. None if there is too little history."""
    if len(rows) < D6M + 1:
        return None
    closes = [r["close"] for r in rows]
    vols = [r["volume"] for r in rows]
    last = closes[-1]
    win = closes[-D52W:]
    hi, lo = max(win), min(win)
    ma200 = sum(closes[-DMA:]) / min(DMA, len(closes))
    v10 = sum(vols[-10:]) / 10
    v60 = sum(vols[-60:]) / min(60, len(vols))
    return {
        "date": rows[-1]["date"],
        "price": round(last, 2),
        "ret_1m": _ret(closes, D1M),
        "ret_3m": _ret(closes, D3M),
        "ret_6m": _ret(closes, D6M),
        "ret_12m": _ret(closes, D12M),
        "vs_200dma": (last / ma200 - 1) * 100,
        "drawdown": (last / hi - 1) * 100,        # <= 0, distance below 52-week high
        "near_high": (last / hi) * 100,           # 100 = at the high
        "range_pos": ((last - lo) / (hi - lo) * 100) if hi > lo else 50.0,
        "vol_surge": (v10 / v60) if v60 > 0 else None,
        "spark": [round(c, 2) for c in closes[-120:]],
    }


def _rank(values: dict[str, float | None]) -> dict[str, float]:
    """0-100 percentile rank across stocks that have a value; missing counts as the median (50)."""
    present = sorted(v for v in values.values() if v is not None)
    n = len(present)
    out = {}
    for k, v in values.items():
        if v is None or n == 0:
            out[k] = 50.0
        else:
            below = sum(1 for x in present if x < v)
            equal = sum(1 for x in present if x == v)
            out[k] = 100 * (below + 0.5 * equal) / n
    return out


def build_ranking(universe: list[dict], metrics: dict[str, dict]) -> list[dict]:
    """Rank stocks by hot score, hottest first. Stocks without metrics are left out."""
    meta = {u["symbol"]: u for u in universe}
    syms = [s for s in metrics if s in meta]
    ranks = {f: _rank({s: metrics[s].get(f) for s in syms}) for f in WEIGHTS}
    items = []
    for s in syms:
        m = metrics[s]
        score = sum(WEIGHTS[f] * ranks[f][s] for f in WEIGHTS)
        item = {"symbol": s, "name": meta[s]["name"], "industry": meta[s]["industry"], "score": round(score, 1), **m}
        for k in ("ret_1m", "ret_3m", "ret_6m", "ret_12m", "vs_200dma", "drawdown", "near_high", "range_pos", "vol_surge"):
            if item.get(k) is not None:
                item[k] = round(item[k], 2)
        item["uptrend"] = bool(m["vs_200dma"] > 0)
        item["on_sale"] = bool(m["drawdown"] <= -DIP_DRAWDOWN)
        items.append(item)
    items.sort(key=lambda x: (-x["score"], x["symbol"]))
    for i, it in enumerate(items, 1):
        it["rank"] = i
    return items


def sector_summary(items: list[dict]) -> list[dict]:
    """Average hot score and 3-month return per industry, hottest first."""
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["industry"] or "Other", []).append(it)
    out = []
    for name, g in groups.items():
        r3 = [x["ret_3m"] for x in g if x.get("ret_3m") is not None]
        out.append({"industry": name, "n": len(g), "score": round(sum(x["score"] for x in g) / len(g), 1),
                    "ret_3m": round(sum(r3) / len(r3), 2) if r3 else None})
    out.sort(key=lambda x: -x["score"])
    return out


def refresh(data_dir: Path | None = None, session: requests.Session | None = None, sleep=time.sleep) -> dict:
    """Fetch the universe + prices, compute the ranking, write data/stocks.json. Returns the payload."""
    s = session or requests.Session()
    universe = fetch_universe(s)
    metrics, failures = {}, []
    for u in universe:
        try:
            m = compute_metrics(fetch_prices(u["symbol"], session=s))
            if m is None:
                failures.append(f"{u['symbol']}: not enough history")
            else:
                metrics[u["symbol"]] = m
        except (StockFetchError, requests.RequestException) as e:
            failures.append(f"{u['symbol']}: {e}")
        sleep(PAUSE)
    if len(failures) > MAX_FAIL_SHARE * len(universe):
        raise StockFetchError(f"{len(failures)}/{len(universe)} stocks failed, e.g. {failures[:3]}")
    items = build_ranking(universe, metrics)
    payload = {
        "date": max(m["date"] for m in metrics.values()),
        "universe": "Nifty 100 (includes the Sensex 30)",
        "count": len(items),
        "failures": failures,
        "weights": WEIGHTS,
        "sectors": sector_summary(items),
        "items": items,
    }
    store.write_json("stocks.json", payload, data_dir)
    return payload
