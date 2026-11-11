"""Daily job.

  python -m tracker.run backfill [--years 12] [--only nifty50,midcap150]
  python -m tracker.run daily [--always-notify]
  python -m tracker.run probe [--index nifty50]   # test one live fetch and print what came back
  python -m tracker.run demo        # SYNTHETIC data into data/demo/ for UI preview only
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from . import compare, fetch, notify, store
from .indices import BY_KEY, INDICES, Index
from .signal import Signal, compute_signal


def _select(only: str | None) -> list[Index]:
    if not only:
        return INDICES
    keys = [k.strip() for k in only.split(",") if k.strip()]
    unknown = [k for k in keys if k not in BY_KEY]
    if unknown:
        raise SystemExit(f"Unknown index key(s): {', '.join(unknown)}. Known: {', '.join(BY_KEY)}")
    return [BY_KEY[k] for k in keys]


def publish(histories: dict[str, list[dict]], signals: dict[str, Signal], data_dir: Path) -> dict:
    """Write everything the dashboard reads: manifest, latest signals, comparison."""
    comp = compare.build_compare(histories, signals)
    store.write_json("indices.json", [
        {"key": i.key, "label": i.label, "group": i.group, "core": i.core}
        for i in INDICES if i.key in signals
    ], data_dir)
    store.write_json("latest.json", {k: s.to_dict() for k, s in signals.items()}, data_dir, indent=2)
    store.write_json("compare.json", comp, data_dir)
    return comp


def cmd_backfill(years: int, only: str | None) -> None:
    end = date.today()
    ok, failed = [], {}
    for idx in _select(only):
        try:
            rows = fetch.fetch_niftyindices(end - timedelta(days=365 * years), end, idx.name)
            if not rows:
                raise fetch.FetchError("no rows returned")
            merged = store.merge_history(store.load_history(idx.key), rows)
            store.save_history(idx.key, merged)
            ok.append(idx.key)
            print(f"{idx.key}: {len(merged)} rows ({merged[0]['date']} -> {merged[-1]['date']})")
        except Exception as e:  # noqa: BLE001
            failed[idx.key] = str(e)
            print(f"{idx.key}: FAILED {e}", file=sys.stderr)
    if not ok:
        raise SystemExit("Backfill failed for every index")
    if failed:
        print(f"Backfill partial. Failed: {', '.join(failed)}", file=sys.stderr)


def cmd_daily(always_notify: bool) -> None:
    prev_state = store.load_state()
    histories: dict[str, list[dict]] = {}
    signals: dict[str, Signal] = {}
    failures: dict[str, str] = {}
    sources: dict[str, str] = {}

    for idx in INDICES:
        history = store.load_history(idx.key)
        try:
            new_rows, source = fetch.fetch_latest(idx.name)
            history = store.merge_history(history, new_rows)
            store.save_history(idx.key, history)
            sources[idx.key] = source
        except fetch.FetchError as e:
            failures[idx.key] = str(e)
            print(f"{idx.key}: fetch failed: {e}", file=sys.stderr)
        if not history:
            continue
        try:
            signals[idx.key] = compute_signal(history)
            histories[idx.key] = history
        except ValueError as e:
            failures.setdefault(idx.key, str(e))
            print(f"{idx.key}: {e}", file=sys.stderr)

    if not signals:
        _alert_text("⚠️ PE tracker: no index data available today. " + "; ".join(f"{k}: {v}" for k, v in failures.items()))
        raise SystemExit(1)

    comp = publish(histories, signals, store.DATA_DIR)
    core = {i.key for i in INDICES if i.core}
    reasons = notify.should_send(
        comp["table"], prev_state, failures, core, always=always_notify, weekly=date.today().weekday() == 0
    )
    print(f"{comp['date']}: {len(signals)} indices, failures={list(failures)}, notify={reasons or 'no'}")
    if reasons:
        notify.send_telegram(
            notify.format_digest(comp["table"], prev_state, comp["insights"], failures, comp["date"])
        )

    new_state = {**prev_state}
    for k, s in signals.items():
        new_state[k] = {"zone": s.zone, "date": s.date, "source": sources.get(k, "stale")}
    store.save_state(new_state)
    if failures and len(failures) == len(INDICES):
        raise SystemExit(1)


def cmd_probe(index_key: str) -> None:
    """Fetch the last 30 days for one index from each source and print the outcome. For debugging."""
    idx = BY_KEY[index_key]
    end = date.today()
    for label, call in (
        ("niftyindices", lambda: fetch.fetch_niftyindices(end - timedelta(days=30), end, idx.name)),
        ("nse allIndices", lambda: [fetch.fetch_nse_today(idx.name)]),
    ):
        try:
            rows = call()
            print(f"{label}: OK, {len(rows)} rows, latest {rows[-1] if rows else None}")
        except Exception as e:  # noqa: BLE001
            print(f"{label}: FAILED {e}")


def _alert_text(msg: str) -> None:
    print(msg, file=sys.stderr)
    try:
        notify.send_telegram(msg)
    except Exception as e:  # noqa: BLE001
        print(f"Also failed to send alert: {e}", file=sys.stderr)


# --- demo -----------------------------------------------------------------------------
# (mean PE, mean-reversion speed, market beta, idiosyncratic vol, yield base)
_DEMO = {
    "nifty50": (22.0, 0.020, 1.0, 0.18, 1.3),
    "niftynext50": (24.0, 0.018, 1.2, 0.25, 1.4),
    "nifty100": (22.5, 0.020, 1.0, 0.18, 1.3),
    "nifty500": (23.5, 0.018, 1.1, 0.22, 1.2),
    "midcap150": (28.0, 0.015, 1.4, 0.35, 0.9),
    "smallcap250": (24.0, 0.012, 1.6, 0.50, 0.8),
    "niftybank": (15.5, 0.022, 1.1, 0.30, 1.1),
    "niftyit": (26.0, 0.015, 0.6, 0.55, 2.2),
}


def cmd_demo() -> None:
    """Synthetic data so the dashboard can be previewed offline. Written to data/demo/, never to real files."""
    out = store.DATA_DIR / "demo"
    out.mkdir(parents=True, exist_ok=True)
    random.seed(7)
    days = []
    d = date.today() - timedelta(days=365 * 12)
    while d <= date.today():
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    market = [random.gauss(0, 0.22) for _ in days]
    histories, signals = {}, {}
    for i, idx in enumerate(INDICES):
        mu, k, beta, vol, dy0 = _DEMO[idx.key]
        rng = random.Random(100 + i)
        pe, rows = mu, []
        for n, day in enumerate(days):
            pe += k * (mu - pe) + beta * market[n] + rng.gauss(0, vol)
            pe = max(mu * 0.5, pe)
            rows.append({"date": day.isoformat(), "pe": round(pe, 2), "pb": round(pe * 0.18, 2),
                         "div_yield": round(max(0.3, dy0 + math.sin(n / 300 + i) * 0.2), 2)})
        store.write_json(f"{idx.key}.json", rows, out)
        histories[idx.key] = rows
        signals[idx.key] = compute_signal(rows)
    publish(histories, signals, out)
    print(f"Demo data for {len(INDICES)} indices in {out}. SYNTHETIC, not real market data.")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--years", type=int, default=12)
    b.add_argument("--only", default=None, help="comma-separated index keys")
    d = sub.add_parser("daily")
    d.add_argument("--always-notify", action="store_true")
    pr = sub.add_parser("probe")
    pr.add_argument("--index", default="nifty50", choices=list(BY_KEY))
    sub.add_parser("demo")
    a = p.parse_args()
    if a.cmd == "backfill":
        cmd_backfill(a.years, a.only)
    elif a.cmd == "daily":
        cmd_daily(a.always_notify)
    elif a.cmd == "probe":
        cmd_probe(a.index)
    else:
        cmd_demo()


if __name__ == "__main__":
    main()
