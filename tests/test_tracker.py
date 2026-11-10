import json
from datetime import date, timedelta

import pytest

from tracker import fetch, notify, store
from tracker.signal import classify, compute_signal, percentile_rank


def make_rows(n=400, start_pe=20.0, last_pe=None):
    rows = []
    d = date(2024, 1, 1)
    for i in range(n):
        rows.append({"date": (d + timedelta(days=i)).isoformat(), "pe": start_pe + (i % 10) * 0.5})
    if last_pe is not None:
        rows[-1]["pe"] = last_pe
    return rows


# ---- signal ----------------------------------------------------------------
def test_percentile_rank():
    assert percentile_rank([1, 2, 3, 4], 2) == 50.0
    assert percentile_rank([1, 2, 3, 4], 0) == 0.0
    assert percentile_rank([1, 2, 3, 4], 9) == 100.0


def test_classify_boundaries():
    assert classify(25.0) == "BUY"
    assert classify(25.1) == "NEUTRAL"
    assert classify(74.9) == "NEUTRAL"
    assert classify(75.0) == "EXPENSIVE"


def test_buy_zone_when_pe_is_lowest():
    sig = compute_signal(make_rows(last_pe=5.0))
    assert sig.zone == "BUY"
    assert sig.z_score < 0


def test_expensive_zone_when_pe_is_highest():
    sig = compute_signal(make_rows(last_pe=60.0))
    assert sig.zone == "EXPENSIVE"
    assert sig.z_score > 0


def test_too_little_history_raises():
    with pytest.raises(ValueError):
        compute_signal(make_rows(n=50))


def test_flat_series_does_not_divide_by_zero():
    rows = [{"date": (date(2024, 1, 1) + timedelta(days=i)).isoformat(), "pe": 20.0} for i in range(300)]
    assert compute_signal(rows).z_score == 0.0


# ---- fetch parsing -----------------------------------------------------------
NIFTYINDICES_FIXTURE = {
    "d": json.dumps(
        [
            {"Index Name": "NIFTY 50", "DATE": "07 Nov 2025", "pe": "22.31", "pb": "3.5", "divYield": "1.3"},
            {"Index Name": "NIFTY 50", "DATE": "06 Nov 2025", "pe": "-", "pb": "3.5", "divYield": "1.3"},
            {"Index Name": "NIFTY 50", "DATE": "05 Nov 2025", "pe": "22.0", "pb": "", "divYield": ""},
        ]
    )
}


def test_parse_niftyindices_skips_bad_pe_and_normalises_dates():
    rows = fetch.parse_niftyindices(NIFTYINDICES_FIXTURE)
    assert [r["date"] for r in rows] == ["2025-11-07", "2025-11-05"]
    assert rows[0]["pe"] == 22.31
    assert rows[1]["pb"] is None


def test_parse_niftyindices_missing_field():
    with pytest.raises(fetch.FetchError):
        fetch.parse_niftyindices({})


def test_parse_nse_all_indices():
    payload = {"data": [{"index": "NIFTY 50", "pe": "21.9", "pb": "3.4", "dy": "1.2"}]}
    row = fetch.parse_nse_all_indices(payload)
    assert row["pe"] == 21.9 and row["div_yield"] == 1.2


def test_parse_nse_missing_index():
    with pytest.raises(fetch.FetchError):
        fetch.parse_nse_all_indices({"data": [{"index": "NIFTY BANK", "pe": "10"}]})


# ---- store / notify ------------------------------------------------------------
def test_merge_history_dedupes_and_sorts():
    merged = store.merge_history(
        [{"date": "2025-01-02", "pe": 20}, {"date": "2025-01-01", "pe": 19}],
        [{"date": "2025-01-02", "pe": 21}, {"date": "2025-01-03", "pe": 22}],
    )
    assert [r["date"] for r in merged] == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert merged[1]["pe"] == 21


def test_format_signal_buy_message():
    sig = compute_signal(make_rows(last_pe=5.0))
    text = notify.format_signal(sig, prev_zone="NEUTRAL")
    assert "BUY" in text and "Zone changed" in text and "not financial advice" in text


def test_send_telegram_requires_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError):
        notify.send_telegram("hi")
