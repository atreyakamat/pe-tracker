"""Tiny JSON file store for PE history and alert state."""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_FILE = DATA_DIR / "nifty50_pe.json"
STATE_FILE = DATA_DIR / "state.json"


def load_history(path: Path = HISTORY_FILE) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def merge_history(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    """Merge by date; newer rows win. Returns date-sorted list."""
    by_date = {r["date"]: r for r in existing}
    for r in new_rows:
        by_date[r["date"]] = r
    return [by_date[k] for k in sorted(by_date)]


def save_history(rows: list[dict], path: Path = HISTORY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, separators=(",", ":")))


def load_state(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
