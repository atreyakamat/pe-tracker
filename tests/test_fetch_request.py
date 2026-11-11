import json
from datetime import date

import pytest

from tracker import fetch
from tracker.indices import BY_KEY, INDICES


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(fetch, "REQUEST_PAUSE", 0)


class FakeResp:
    def __init__(self, payload=None, status=200, text="", content_type="application/json"):
        self._payload, self.status_code, self.text = payload, status, text
        self.headers = {"Content-Type": content_type}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responder):
        self.responder, self.calls = responder, []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responder(len(self.calls))


def payload(rows):
    """Current niftyindices format: a bare JSON array."""
    return rows


ROW = {"RequestNumber": "pepb1", "Index Name": "Nifty 50", "DATE": "07 Nov 2025", "pe": "22.31", "pb": "3.5", "divYield": "1.3"}


def test_request_uses_known_endpoint_and_body_format():
    s = FakeSession(lambda n: FakeResp(payload([ROW])))
    rows = fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), "NIFTY 50", session=s)
    url, kw = s.calls[0]
    assert url == "https://www.niftyindices.com/BackPage/getpepbHistoricaldataDBtoString"
    assert kw["json"] == {
        "cinfo": "{'name':'NIFTY 50','startDate':'01-Nov-2025','endDate':'10-Nov-2025','indexName':'NIFTY 50'}"
    }
    assert kw["allow_redirects"] is False  # a redirect means the endpoint moved (login page), never follow it
    assert kw["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert kw["headers"]["Referer"].endswith("/reports/historical-data")
    assert rows[0]["date"] == "2025-11-07" and rows[0]["pe"] == 22.31


def test_non_json_reply_gives_clear_error_with_snippet():
    s = FakeSession(lambda n: FakeResp(None, text="<html><body>Not Found</body></html>", content_type="text/html"))
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), session=s)
    msg = str(e.value)
    assert "non-JSON" in msg and "text/html" in msg and "Not Found" in msg


def test_http_error_includes_body_snippet():
    s = FakeSession(lambda n: FakeResp(None, status=403, text="Access Denied"))
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), session=s)
    assert "403" in str(e.value) and "Access Denied" in str(e.value)


def test_long_range_is_chunked_and_deduped():
    # Same row returned for every chunk, so output must be deduped to one row.
    s = FakeSession(lambda n: FakeResp(payload([ROW])))
    rows = fetch.fetch_niftyindices(date(2015, 1, 1), date(2025, 11, 10), session=s)
    assert len(s.calls) > 3
    assert len(rows) == 1
    # every request spans at most the site's 1-year limit
    from datetime import datetime
    for _, kw in s.calls:
        c = kw["json"]["cinfo"]
        a = datetime.strptime(c.split("'startDate':'")[1].split("'")[0], "%d-%b-%Y")
        b = datetime.strptime(c.split("'endDate':'")[1].split("'")[0], "%d-%b-%Y")
        assert (b - a).days <= 365
    # chunks must not overlap or leave gaps
    starts = [c[1]["json"]["cinfo"].split("'startDate':'")[1].split("'")[0] for c in s.calls]
    assert starts[0] == "01-Jan-2015" and len(set(starts)) == len(starts)


def test_empty_response_is_ok_not_error():
    s = FakeSession(lambda n: FakeResp(payload([])))
    assert fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), session=s) == []


def test_legacy_wrapped_format_still_parses():
    s = FakeSession(lambda n: FakeResp({"d": json.dumps([ROW])}))
    assert len(fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), session=s)) == 1


def test_values_like_dot95_and_blank_parse():
    row = {**ROW, "pe": "32.25", "pb": "3.39", "divYield": ".76"}
    blank = {**ROW, "DATE": "06 Nov 2025", "pe": "21.0", "pb": "", "divYield": ""}
    rows = fetch.parse_niftyindices([row, blank])
    assert rows[0]["div_yield"] == 0.76 and rows[1]["pb"] is None


def test_redirect_to_login_is_a_clear_error():
    s = FakeSession(lambda n: FakeResp(None, status=302, text='{"Message":"There was an error processing the request."}'))
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), session=s)
    assert "302" in str(e.value)


def test_smallcap_uses_niftyindices_own_name():
    idx = BY_KEY["smallcap250"]
    assert idx.ni_trading == "NIFTY SMLCAP 250"      # NSE-style name returns 0 rows on niftyindices
    assert idx.name == "NIFTY SMALLCAP 250"          # but NSE allIndices needs this one
    assert BY_KEY["nifty50"].ni_trading == "NIFTY 50" and BY_KEY["nifty50"].ni_index_name == "Nifty 50"


def test_fetch_latest_sends_niftyindices_names(monkeypatch):
    seen = {}

    def fake_ni(start, end, name, index_name=None, session=None):
        seen["ni"] = (name, index_name)
        return [{"date": "2026-11-09", "pe": 32.0, "pb": 3.4, "div_yield": 0.8}]

    monkeypatch.setattr(fetch, "fetch_niftyindices", fake_ni)
    rows, source = fetch.fetch_latest(BY_KEY["smallcap250"])
    assert seen["ni"] == ("NIFTY SMLCAP 250", "NIFTY Smallcap 250")
    assert source == "niftyindices" and rows[0]["pe"] == 32.0


def test_fetch_latest_never_falls_back_to_nse_for_history(monkeypatch):
    """NSE allIndices stamps yesterday's PE with today's date, so it must not feed stored history."""
    monkeypatch.setattr(fetch, "fetch_niftyindices", lambda *a, **k: [])
    called = []
    monkeypatch.setattr(fetch, "fetch_nse_today", lambda *a, **k: called.append(1))
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch_latest(BY_KEY["smallcap250"])
    assert "no rows" in str(e.value) and not called


def test_fetch_latest_wraps_errors(monkeypatch):
    def boom(*a, **k):
        raise fetch.FetchError("HTTP 302")

    monkeypatch.setattr(fetch, "fetch_niftyindices", boom)
    with pytest.raises(fetch.FetchError) as e:
        fetch.fetch_latest(BY_KEY["nifty50"])
    assert "HTTP 302" in str(e.value)


def test_every_index_has_names_for_both_sources():
    for i in INDICES:
        assert i.ni_trading and i.ni_index_name and i.name
