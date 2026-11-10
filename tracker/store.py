"""Tiny JSON file store: one history file per index, plus alert state and compare output."""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def history_path(key: str, data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / f"{key}.json"


def load_history(key: str, data_dir: Path | None = None) -> list[dict]:
    path = history_path(key, data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def merge_history(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    """Merge by date; newer rows win. Returns date-sorted list."""
    by_date = {r["date"]: r for r in existing}
    for r in new_rows:
        by_date[r["date"]] = r
    return [by_date[k] for k in sorted(by_date)]


def save_history(key: str, rows: list[dict], data_dir: Path | None = None) -> None:
    data_dir = data_dir or DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    history_path(key, data_dir).write_text(json.dumps(rows, separators=(",", ":")))


def load_state(path: Path | None = None) -> dict:
    """{index_key: {"zone": ..., "date": ..., "source": ...}}"""
    path = path or DATA_DIR / "state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or DATA_DIR / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def write_json(name: str, obj, data_dir: Path | None = None, indent: int | None = None) -> None:
    data_dir = data_dir or DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / name).write_text(json.dumps(obj, indent=indent, separators=None if indent else (",", ":")))
