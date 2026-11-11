from datetime import date, timedelta

import pytest

from tracker import planner


def make(n_days=1800, pe0=20.0, px0=100.0, pe_step=0.0, px_step=0.0):
    d0 = date(2018, 1, 1)
    pe, px = [], []
    for i in range(n_days):
        d = (d0 + timedelta(days=i)).isoformat()
        pe.append({"date": d, "pe": pe0 + pe_step * i, "pb": 3.0, "div_yield": 1.2})
        px.append({"date": d, "close": px0 + px_step * i, "volume": 0.0})
    return pe, px


def test_zone_uses_only_past_data_and_needs_history():
    pe, _ = make(n_days=300)
    assert planner.pe_zone(pe, pe[-1]["date"]) is None            # < MIN_HISTORY days
    pe, _ = make()
    # strictly rising PE -> latest is the highest -> EXPENSIVE
    pe, _ = make(pe_step=0.01)
    assert planner.pe_zone(pe, pe[-1]["date"])[0] == "EXPENSIVE"
    # strictly falling PE -> latest is the lowest -> BUY
    pe, _ = make(pe0=40, pe_step=-0.01)
    assert planner.pe_zone(pe, pe[-1]["date"])[0] == "BUY"


def test_zone_outlier_today_is_expensive_not_distorting():
    pe, _ = make()
    pe[-1]["pe"] = 5000.0
    assert planner.pe_zone(pe, pe[-1]["date"]) == ("EXPENSIVE", 100.0)


def test_drawdown_and_dip_tiers():
    assert planner.drawdown([100, 110, 99]) == pytest.approx(-10.0)
    assert planner.dip_extra(-4) == 0 and planner.dip_extra(-10) == 0.5 and planner.dip_extra(-25) == 1.0


def test_extra_is_capped():
    assert planner.extra_multiple("BUY", -25) == planner.MAX_EXTRA
    assert planner.extra_multiple("EXPENSIVE", -2) == 0.0


def test_xirr_known_values():
    r = planner.xirr([("2020-01-01", -1000.0), ("2021-01-01", 1100.0)])
    assert r == pytest.approx(0.10, abs=0.005)
    assert planner.xirr([("2020-01-01", -1000.0)]) is None


def test_backtest_flat_market_returns_what_was_paid():
    pe, px = make()
    bt = planner.backtest(pe, px)
    s = bt["summary"]
    assert s["plain"]["value"] == s["plain"]["paid"]               # flat price, nothing gained or lost
    assert s["scaled"]["value"] == s["scaled"]["paid"]             # cash + units both valued at cost
    assert s["core_plus"]["paid"] >= s["plain"]["paid"]            # extra can only add money
    assert s["plain"]["cash_left"] == 0 and bt["months"] >= 12


def test_core_plus_never_cuts_the_sip():
    pe, px = make(pe_step=0.01, px_step=0.05)                      # expensive and rising: extra never triggers
    bt = planner.backtest(pe, px)
    assert bt["summary"]["core_plus"]["paid"] == bt["summary"]["plain"]["paid"]
    assert bt["extra"]["buys"] == 0


def test_advice_amounts_and_levels():
    pe, px = make(pe0=40, pe_step=-0.01, px_step=0.0)
    px[-1]["close"] = 85.0                                         # 15% below the 52-week high of 100
    a = planner.advice(pe, px)
    assert a["zone"] == "BUY" and a["base_amount"] == planner.SIP_AMOUNT
    assert a["extra_multiple"] == 1.5                              # BUY 1.0 + dip 0.5
    assert a["total_amount"] == round(planner.SIP_AMOUNT * 2.5)
