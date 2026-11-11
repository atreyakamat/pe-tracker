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
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text, *a, **k: sent.append(text))
    for i, idx in enumerate(INDICES):
        store.save_history(idx.key, history(20 + i))
    return tmp_path, sent


def test_daily_publishes_files_and_sends_digest_when_forced(env, monkeypatch):
    tmp, sent = env
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)
    for f in ("latest.json", "compare.json", "indices.json", "state.json"):
        assert (tmp / f).exists(), f
    assert len(sent) == 1 and "Valuation check" in sent[0]
    state = store.load_state()
    assert set(state) == {i.key for i in INDICES}


def test_one_index_failing_is_reported_but_job_continues(env, monkeypatch):
    tmp, sent = env

    def fake(idx, *a, **k):
        if idx.name == "NIFTY BANK":
            raise fetch.FetchError("blocked")
        return [], "niftyindices"

    monkeypatch.setattr(fetch, "fetch_latest", fake)
    run.cmd_daily(always_notify=False)
    assert len(sent) == 1
    assert "niftybank" in sent[0] and "Could not fetch" in sent[0]
    assert "Nifty 50" in sent[0]  # others still reported from stored data


def test_all_fetches_failing_with_no_data_exits_nonzero_and_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text, *a, **k: sent.append(text))
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: (_ for _ in ()).throw(fetch.FetchError("down")))
    with pytest.raises(SystemExit) as e:
        run.cmd_daily(always_notify=False)
    assert e.value.code == 1
    assert sent and "no index data" in sent[0]


def test_quiet_day_sends_nothing(env, monkeypatch):
    tmp, sent = env
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)          # first run records state; fixture data ends EXPENSIVE for all
    assert all(r["zone"] == "EXPENSIVE" for r in __import__("json").loads((tmp / "compare.json").read_text())["table"])
    sent.clear()
    # Tuesday, so no weekly digest. No zone change, no core index in BUY, no failures => silence.
    monkeypatch.setattr(run, "date", type("D", (), {"today": staticmethod(lambda: date(2026, 11, 10))}))
    run.cmd_daily(always_notify=False)
    assert sent == []


def test_telegram_failure_keeps_data_but_not_state_and_fails_the_run(env, monkeypatch):
    tmp, sent = env
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: ([], "niftyindices"))

    def boom(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(notify, "send_telegram", boom)
    with pytest.raises(SystemExit) as e:
        run.cmd_daily(always_notify=True)
    assert "notification failed" in str(e.value)
    assert (tmp / "compare.json").exists()        # dashboard data still published
    assert not (tmp / "state.json").exists()      # so the alert is retried next run


def test_no_channel_configured_still_saves_state_and_passes(env, monkeypatch, capsys):
    tmp, sent = env
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)                       # must NOT raise
    assert sent == [] and (tmp / "state.json").exists()
    assert "No notification channel configured" in capsys.readouterr().out


def test_github_issue_channel_used_when_only_github_configured(env, monkeypatch):
    tmp, sent = env
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "gt")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    issues = []
    monkeypatch.setattr(notify, "send_github_issue", lambda t, b: issues.append((t, b)))
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)
    assert sent == [] and len(issues) == 1
    assert "Valuation check" in issues[0][1] and (tmp / "state.json").exists()


def test_one_channel_failing_is_fine_if_the_other_works(env, monkeypatch):
    tmp, sent = env
    monkeypatch.setenv("GITHUB_TOKEN", "gt")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    monkeypatch.setattr(notify, "send_github_issue", lambda t, b: (_ for _ in ()).throw(RuntimeError("api down")))
    monkeypatch.setattr(fetch, "fetch_latest", lambda idx, *a, **k: ([], "niftyindices"))
    run.cmd_daily(always_notify=True)                       # telegram worked -> run passes, state saved
    assert len(sent) == 1 and (tmp / "state.json").exists()
