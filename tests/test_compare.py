from datetime import date, timedelta

from tracker import compare, notify, store
from tracker.indices import BY_KEY, INDICES, PAIRS
from tracker.signal import compute_signal


def series(n=400, base=20.0, step=0.1, start=date(2024, 1, 1), pb=3.0, dy=1.2):
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "pe": base + (i % 10) * step, "pb": pb + (i % 7) * 0.01,
         "div_yield": dy + (i % 5) * 0.01}
        for i in range(n)
    ]


# ---- config ---------------------------------------------------------------------------
def test_index_keys_unique_and_pairs_valid():
    keys = [i.key for i in INDICES]
    assert len(keys) == len(set(keys))
    for a, b in PAIRS:
        assert a in BY_KEY and b in BY_KEY


# ---- composite ----------------------------------------------------------------------------
def test_composite_present_and_bounded():
    sig = compute_signal(series())
    assert sig.composite is not None and 0 <= sig.composite <= 100
    assert sig.pb_percentile is not None and sig.dy_percentile is not None


def test_composite_falls_back_to_pe_when_pb_and_yield_missing():
    rows = series()
    for r in rows:
        r["pb"] = None
        r["div_yield"] = None
    sig = compute_signal(rows)
    assert sig.pb_percentile is None and sig.dy_percentile is None
    assert sig.composite == round(sig.percentile, 1)


def test_high_dividend_yield_makes_composite_cheaper():
    cheap = series()
    cheap[-1]["div_yield"] = 5.0   # highest yield in window => cheapest on that leg
    rich = series()
    rich[-1]["div_yield"] = 0.1
    assert compute_signal(cheap).composite < compute_signal(rich).composite


# ---- relative valuation -----------------------------------------------------------------------
def test_relative_premium_math_and_alignment():
    a = series(base=30.0)
    b = series(base=20.0)
    b = b[10:]  # b is missing the first 10 dates, A has them
    st = compare.relative_stats(a, b)
    assert st is not None
    assert st["percentile"] <= 100 and st["min"] <= st["premium"] <= st["max"]
    rel = compare.relative_series(a, b)
    assert len(rel) == len(b)
    assert abs(rel[0]["premium"] - ((a[10]["pe"] / b[0]["pe"]) - 1) * 100) < 1e-9


def test_relative_none_when_too_little_overlap():
    assert compare.relative_stats(series(n=100), series(n=100)) is None


# ---- correlation -----------------------------------------------------------------------------------
def test_correlation_perfect_and_inverse():
    base = series(n=500)
    inverse = [{**r, "pe": 60.0 - r["pe"]} for r in base]
    c = compare.correlation({"a": base, "b": base, "c": inverse})
    m = c["matrix"]
    assert m[0][0] == 1.0
    assert m[0][1] == 1.0
    assert m[0][2] < -0.5


def test_correlation_skips_short_history():
    c = compare.correlation({"a": series(n=500), "b": series(n=50)})
    assert c["keys"] == ["a"]


# ---- table and insights --------------------------------------------------------------------------------
def make_signals():
    cheap = series()
    cheap[-1]["pe"] = 5.0
    rich = series()
    rich[-1]["pe"] = 60.0
    return {"nifty50": compute_signal(rich), "midcap150": compute_signal(cheap)}, {"nifty50": rich, "midcap150": cheap}


def test_table_sorted_cheapest_first_and_insights_name_extremes():
    sigs, hist = make_signals()
    comp = compare.build_compare(hist, sigs)
    assert [r["key"] for r in comp["table"]] == ["midcap150", "nifty50"]
    text = " ".join(comp["insights"])
    assert "Cheapest" in text and "Nifty Midcap 150" in text and "BUY zone" in text


# ---- notifications ------------------------------------------------------------------------------------------
TABLE = [
    {"key": "nifty50", "label": "Nifty 50", "zone": "BUY", "pe": 20.4, "pe_percentile": 19.0},
    {"key": "niftyit", "label": "Nifty IT", "zone": "NEUTRAL", "pe": 28.0, "pe_percentile": 60.0},
]


def test_quiet_when_nothing_changed_and_core_not_in_buy():
    state = {"nifty50": {"zone": "BUY"}, "niftyit": {"zone": "NEUTRAL"}}
    assert notify.should_send(TABLE, state, {}, core_keys=set()) == []


def test_core_index_in_buy_triggers_daily_reminder():
    state = {"nifty50": {"zone": "BUY"}, "niftyit": {"zone": "NEUTRAL"}}
    assert notify.should_send(TABLE, state, {}, core_keys={"nifty50"})


def test_zone_change_failure_weekly_and_forced_each_trigger():
    state = {"nifty50": {"zone": "NEUTRAL"}, "niftyit": {"zone": "NEUTRAL"}}
    assert any("NEUTRAL -> BUY" in r for r in notify.should_send(TABLE, state, {}, set()))
    same = {"nifty50": {"zone": "BUY"}, "niftyit": {"zone": "NEUTRAL"}}
    assert notify.should_send(TABLE, same, {"niftybank": "x"}, set())
    assert notify.should_send(TABLE, same, {}, set(), weekly=True)
    assert notify.should_send(TABLE, same, {}, set(), always=True)


def test_first_run_with_no_state_is_quiet_unless_core_in_buy():
    assert notify.should_send(TABLE, {}, {}, core_keys=set()) == []


def test_digest_mentions_change_failures_and_disclaimer():
    state = {"nifty50": {"zone": "NEUTRAL"}}
    text = notify.format_digest(TABLE, state, ["insight one", "insight two"], {"niftybank": "boom"}, "2026-11-10")
    assert "was NEUTRAL" in text and "niftybank" in text and "not financial advice" in text and "insight one" in text
    assert len(text) < 4096


# ---- store ----------------------------------------------------------------------------------------------------------
def test_store_roundtrip_per_index(tmp_path):
    store.save_history("nifty50", [{"date": "2025-01-01", "pe": 20}], tmp_path)
    store.save_history("niftybank", [{"date": "2025-01-01", "pe": 15}], tmp_path)
    assert store.load_history("nifty50", tmp_path)[0]["pe"] == 20
    assert store.load_history("niftybank", tmp_path)[0]["pe"] == 15
    assert store.load_history("missing", tmp_path) == []
