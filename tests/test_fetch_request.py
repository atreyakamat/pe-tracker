import json
from datetime import date

import pytest

from tracker import fetch


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
    return {"d": json.dumps(rows)}


ROW = {"Index Name": "NIFTY 50", "DATE": "07 Nov 2025", "pe": "22.31", "pb": "3.5", "divYield": "1.3"}


def test_request_uses_known_endpoint_and_body_format():
    s = FakeSession(lambda n: FakeResp(payload([ROW])))
    rows = fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), "NIFTY 50", session=s)
    url, kw = s.calls[0]
    assert url.endswith("/Backpage.aspx/getpepbHistoricaldataDBtoString")
    assert kw["json"] == {
        "cinfo": "{'name':'NIFTY 50','startDate':'01-Nov-2025','endDate':'10-Nov-2025','indexName':'NIFTY 50'}"
    }
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
    # chunks must not overlap or leave gaps
    starts = [c[1]["json"]["cinfo"].split("'startDate':'")[1].split("'")[0] for c in s.calls]
    assert starts[0] == "01-Jan-2015" and len(set(starts)) == len(starts)


def test_empty_response_is_ok_not_error():
    s = FakeSession(lambda n: FakeResp(payload([])))
    assert fetch.fetch_niftyindices(date(2025, 11, 1), date(2025, 11, 10), session=s) == []
