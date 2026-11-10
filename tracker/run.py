"""Daily job.

  python -m tracker.run backfill [--years 12]   one-time: load full PE history
  python -m tracker.run daily                    fetch latest, compute signal, alert
  python -m tracker.run demo                     write synthetic data for UI preview ONLY
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date, timedelta

from . import fetch, notify, store
from .signal import compute_signal


def cmd_backfill(years: int) -> None:
    end = date.today()
    rows = fetch.fetch_niftyindices(end - timedelta(days=365 * years), end)
    if not rows:
        raise SystemExit("Backfill returned no rows")
    merged = store.merge_history(store.load_history(), rows)
    store.save_history(merged)
    print(f"Saved {len(merged)} rows ({merged[0]['date']} -> {merged[-1]['date']})")


def _write_latest(sig) -> None:
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (store.DATA_DIR / "latest.json").write_text(json.dumps(sig.to_dict(), indent=2))


def cmd_daily(always_notify: bool) -> None:
    state = store.load_state()
    try:
        new_rows, source = fetch.fetch_latest()
    except fetch.FetchError as e:
        # Never fail silently: tell the user the data is stale.
        msg = f"⚠️ PE tracker could not fetch data today: {e}"
        print(msg, file=sys.stderr)
        try:
            notify.send_telegram(msg)
        except Exception as ne:  # noqa: BLE001
            print(f"Also failed to send alert: {ne}", file=sys.stderr)
        raise SystemExit(1)

    history = store.merge_history(store.load_history(), new_rows)
    store.save_history(history)
    sig = compute_signal(history)
    _write_latest(sig)

    prev = state.get("zone")
    changed = prev != sig.zone
    print(f"[{source}] {sig.date} PE={sig.pe} zone={sig.zone} pct={sig.percentile} (prev={prev})")

    # Alert when the zone changes, or every day while in BUY zone, or when forced.
    if changed or sig.zone == "BUY" or always_notify:
        notify.send_telegram(notify.format_signal(sig, prev))

    store.save_state({"zone": sig.zone, "date": sig.date, "source": source})


def cmd_demo() -> None:
    """Synthetic mean-reverting PE series so the dashboard can be previewed offline.
    Written to data/demo.json, never to the real history file."""
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(7)
    rows, pe, d = [], 22.0, date.today() - timedelta(days=365 * 12)
    while d <= date.today():
        if d.weekday() < 5:
            pe += 0.02 * (22 - pe) + random.gauss(0, 0.25)
            pe = max(12.0, pe)
            rows.append({"date": d.isoformat(), "pe": round(pe, 2),
                         "pb": round(pe * 0.19, 2), "div_yield": round(1.4 + math.sin(len(rows) / 300) * 0.2, 2)})
        d += timedelta(days=1)
    (store.DATA_DIR / "demo.json").write_text(json.dumps(rows, separators=(",", ":")))
    sig = compute_signal(rows)
    (store.DATA_DIR / "demo_latest.json").write_text(json.dumps(sig.to_dict(), indent=2))
    print(f"Demo data: {len(rows)} rows. SYNTHETIC, not real market data.")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--years", type=int, default=12)
    d = sub.add_parser("daily")
    d.add_argument("--always-notify", action="store_true")
    sub.add_parser("demo")
    a = p.parse_args()
    if a.cmd == "backfill":
        cmd_backfill(a.years)
    elif a.cmd == "daily":
        cmd_daily(a.always_notify)
    else:
        cmd_demo()


if __name__ == "__main__":
    main()
