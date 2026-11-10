"""End-to-end test of the daily job with network and Telegram mocked."""
from datetime import date, timedelta

import pytest

from tracker import fetch, notify, run, store
from tracker.indices import INDICES


def history(base, n=400):
    start = date.today() - timedelta(days=n)
    return [{"date": (start + timedelta(days=i)).isoformat(), "pe": base + (i % 10) * 0.1, "pb": 3.0, "div_yield": 1.2}
            for i in range(n)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text, *a, **k: sent.append(text))
    for i, idx in enumerate(INDICES):
        store.save_history(idx.key, history(20 + i))
    return tmp_path, sent


def test_daily_publishes_files_and_sends_digest_when_forced(env, monkeypatch):
    tmp, sent = env
    monkeypatch.setattr(fetch, "fetch_latest", lambda name, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)
    for f in ("latest.json", "compare.json", "indices.json", "state.json"):
        assert (tmp / f).exists(), f
    assert len(sent) == 1 and "Valuation check" in sent[0]
    state = store.load_state()
    assert set(state) == {i.key for i in INDICES}


def test_one_index_failing_is_reported_but_job_continues(env, monkeypatch):
    tmp, sent = env

    def fake(name, *a, **k):
        if name == "NIFTY BANK":
            raise fetch.FetchError("blocked")
        return [], "niftyindices"

    monkeypatch.setattr(fetch, "fetch_latest", fake)
    run.cmd_daily(always_notify=False)
    assert len(sent) == 1
    assert "niftybank" in sent[0] and "Could not fetch" in sent[0]
    assert "Nifty 50" in sent[0]  # others still reported from stored data


def test_all_fetches_failing_with_no_data_exits_nonzero_and_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text, *a, **k: sent.append(text))
    monkeypatch.setattr(fetch, "fetch_latest", lambda name, *a, **k: (_ for _ in ()).throw(fetch.FetchError("down")))
    with pytest.raises(SystemExit) as e:
        run.cmd_daily(always_notify=False)
    assert e.value.code == 1
    assert sent and "no index data" in sent[0]


def test_quiet_day_sends_nothing(env, monkeypatch):
    tmp, sent = env
    monkeypatch.setattr(fetch, "fetch_latest", lambda name, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)          # first run records state; fixture data ends EXPENSIVE for all
    assert all(r["zone"] == "EXPENSIVE" for r in __import__("json").loads((tmp / "compare.json").read_text())["table"])
    sent.clear()
    # Tuesday, so no weekly digest. No zone change, no core index in BUY, no failures => silence.
    monkeypatch.setattr(run, "date", type("D", (), {"today": staticmethod(lambda: date(2026, 11, 10))}))
    run.cmd_daily(always_notify=False)
    assert sent == []
