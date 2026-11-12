from datetime import date, timedelta

import pytest

from tracker import stocks


def rows(n=300, start=100.0, step=0.0, vol=1000.0, last_vol=None):
    d0 = date(2025, 1, 1)
    out = []
    for i in range(n):
        out.append({"date": (d0 + timedelta(days=i)).isoformat(), "close": start + step * i, "volume": vol})
    if last_vol is not None:
        for r in out[-10:]:
            r["volume"] = last_vol
    return out


def test_parse_universe_handles_bom_and_blank_symbols():
    text = "﻿Company Name,Industry,Symbol,Series,ISIN Code\nABB India Ltd.,Capital Goods,ABB,EQ,X\nNo Symbol,Misc,,EQ,Y\n"
    assert stocks.parse_universe(text) == [{"symbol": "ABB", "name": "ABB India Ltd.", "industry": "Capital Goods"}]


def test_yahoo_symbol_encodes_special_characters():
    assert stocks.yahoo_symbol("M&M") == "M%26M.NS"
    assert stocks.yahoo_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO.NS"


def test_parse_chart_skips_null_closes_and_dedupes_dates():
    t = 1_700_000_000
    payload = {"chart": {"result": [{"timestamp": [t, t + 60, t + 86400], "indicators": {
        "quote": [{"close": [10.0, 11.0, None], "volume": [5, 6, 7]}], "adjclose": [{"adjclose": [10.0, 11.0, None]}]}}]}}
    out = stocks.parse_chart(payload)
    assert len(out) == 1 and out[0]["close"] == 11.0   # same IST day -> last bar wins; None day dropped


def test_parse_chart_error_raises():
    with pytest.raises(stocks.StockFetchError):
        stocks.parse_chart({"chart": {"result": None, "error": {"code": "Not Found"}}})


def test_metrics_need_enough_history():
    assert stocks.compute_metrics(rows(n=100)) is None


def test_metrics_uptrend_and_drawdown():
    m = stocks.compute_metrics(rows(step=0.5))
    assert m["ret_1m"] > 0 and m["vs_200dma"] > 0 and m["drawdown"] == pytest.approx(0, abs=1e-9)
    falling = rows(step=0.5)
    falling[-1]["close"] = falling[-2]["close"] * 0.8
    m2 = stocks.compute_metrics(falling)
    assert m2["drawdown"] < -15 and m2["near_high"] < 85


def test_volume_surge():
    m = stocks.compute_metrics(rows(vol=1000, last_vol=3000))
    assert m["vol_surge"] > 1.5
    assert stocks.compute_metrics(rows())["vol_surge"] == pytest.approx(1.0)


def test_ranking_orders_hot_above_cold_and_flags():
    uni = [{"symbol": s, "name": s, "industry": "X"} for s in ("HOT", "COLD", "MID")]
    metrics = {
        "HOT": stocks.compute_metrics(rows(step=1.0, vol=1000, last_vol=2500)),
        "MID": stocks.compute_metrics(rows(step=0.05)),
        "COLD": stocks.compute_metrics(rows(start=400, step=-1.0)),
    }
    ranked = stocks.build_ranking(uni, metrics)
    assert [r["symbol"] for r in ranked] == ["HOT", "MID", "COLD"]
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert ranked[0]["uptrend"] and not ranked[2]["uptrend"] and ranked[2]["on_sale"]
    assert 0 <= ranked[2]["score"] < ranked[0]["score"] <= 100


def test_rank_missing_value_counts_as_median():
    r = stocks._rank({"a": 1.0, "b": 2.0, "c": None})
    assert r["c"] == 50.0 and r["a"] < r["b"]


def test_refresh_tolerates_a_few_failures_but_not_many(tmp_path):
    uni = [{"symbol": f"S{i}", "name": f"S{i}", "industry": "X"} for i in range(100)]
    good = rows(step=0.3)

    def run(bad):
        def fp(sym, range_="2y", session=None):
            if int(sym[1:]) < bad:
                raise stocks.StockFetchError("boom")
            return good
        orig = (stocks.fetch_universe, stocks.fetch_prices)
        stocks.fetch_universe, stocks.fetch_prices = (lambda s=None: uni), fp
        try:
            return stocks.refresh(data_dir=tmp_path, sleep=lambda _: None)
        finally:
            stocks.fetch_universe, stocks.fetch_prices = orig

    p = run(5)
    assert p["count"] == 95 and len(p["failures"]) == 5 and (tmp_path / "stocks.json").exists()
    with pytest.raises(stocks.StockFetchError):
        run(30)
