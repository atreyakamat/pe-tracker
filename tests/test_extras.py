"""Tests for mutual funds (AMFI), the earnings calendar and the planner-tier alert."""
from datetime import date

import pytest

from tracker import earnings, mf, notify, run, store

NAVALL = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Index Funds - Equity Funds)

UTI Mutual Fund

120716;INF789F01XA0;-;UTI Nifty 50 Index Fund - Direct Plan - Growth;Direct;Growth;180.1234;09-Nov-2026
120717;INF789F01XB8;-;UTI Nifty 50 Index Fund - Direct Plan - IDCW;Direct;IDCW;N.A.;09-Nov-2026

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Some AMC

100001;INF0;-;Some Active Large Cap Fund;Direct;Growth;99.9;09-Nov-2026

Open Ended Schemes(Other Scheme - Index Funds)

HDFC Mutual Fund

101281;INF179K01XY2;-;HDFC Nifty 50 Index Fund - Growth;Regular;Growth;230.45;09-Nov-2026
"""


def test_parse_navall_keeps_only_index_funds_with_valid_navs():
    out = mf.parse_navall(NAVALL)
    assert [x["code"] for x in out] == ["120716", "101281"]     # active fund and N.A. NAV dropped
    assert out[0]["nav"] == 180.1234 and out[0]["date"] == "2026-11-09"
    assert "Index Funds" in out[0]["category"]


def test_mf_refresh_rejects_thin_parse(tmp_path, monkeypatch):
    class R:  # fake response
        status_code = 200
        text = NAVALL
    monkeypatch.setattr(mf.requests, "Session", lambda: type("S", (), {"get": lambda self, *a, **k: R()})())
    with pytest.raises(mf.MFError):
        mf.refresh(data_dir=tmp_path)


def test_parse_events_filters_universe_window_and_sorts():
    today = date(2026, 11, 11)
    payload = [
        {"symbol": "TCS", "company": "TCS Ltd", "purpose": "Financial Results", "date": "20-Nov-2026"},
        {"symbol": "NOTOURS", "company": "X", "purpose": "Results", "date": "15-Nov-2026"},
        {"symbol": "INFY", "company": "Infosys", "purpose": "", "date": "12-Nov-2026"},
        {"symbol": "RELIANCE", "company": "RIL", "purpose": "Results", "date": "01-Mar-2027"},   # beyond horizon
        {"symbol": "HDFCBANK", "company": "HDFC Bank", "purpose": "Results", "date": "01-Nov-2026"},  # past
    ]
    out = earnings.parse_events(payload, {"TCS", "INFY", "RELIANCE", "HDFCBANK"}, today)
    assert [x["symbol"] for x in out] == ["INFY", "TCS"]
    assert out[0]["purpose"] == "Board meeting"                 # empty purpose gets a default


def test_planner_tier_alert_fires_on_change_only(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text, *a, **k: sent.append(text))
    a = {"zone": "BUY", "extra_multiple": 1.0, "extra_amount": 12000, "base_amount": 12000,
         "total_amount": 24000, "pe_percentile": 9.0, "nifty": 25255.1, "high_52w": 26328.0,
         "drawdown": -4.1, "date": "2026-11-09", "note": "n"}
    assert run._planner_tier_alert(a) is None
    assert len(sent) == 1 and "24000" in sent[0]
    assert run._planner_tier_alert(a) is None                   # unchanged -> quiet
    assert len(sent) == 1
    a2 = {**a, "zone": "NEUTRAL", "extra_multiple": 0.0, "extra_amount": 0, "total_amount": 12000}
    assert run._planner_tier_alert(a2) is None                  # switched off -> says so once
    assert len(sent) == 2 and "regular SIP" in sent[1]


def test_planner_tier_alert_failure_keeps_state_for_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(notify, "send_telegram", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    a = {"zone": "BUY", "extra_multiple": 1.0, "extra_amount": 12000, "base_amount": 12000,
         "total_amount": 24000, "pe_percentile": 9.0, "nifty": 25255.1, "high_52w": 26328.0,
         "drawdown": -4.1, "date": "2026-11-09", "note": "n"}
    assert run._planner_tier_alert(a) is not None               # reported as an error
    assert not (tmp_path / "planner_state.json").exists()       # so the next run retries


def test_github_issue_send_shape(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gt")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    calls = {}
    class R:
        status_code = 201
        text = ""
    def post(url, json=None, headers=None, timeout=None):
        calls.update(url=url, json=json, auth=headers.get("Authorization"))
        return R()
    monkeypatch.setattr(notify.requests, "post", post)
    notify.send_github_issue("title", "body")
    assert calls["url"].endswith("/repos/me/repo/issues")
    assert calls["json"]["labels"] == ["market-alert"] and calls["auth"] == "Bearer gt"
