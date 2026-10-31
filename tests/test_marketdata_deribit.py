"""Tests for the Deribit loader, using a real snapshot (see tests/data/*.json
provenance blocks). No network access is needed or used."""
import json
from pathlib import Path

import pytest

from vanna.backtest.engine import run_backtest
from vanna.marketdata import (analyze_chain, load_chain_snapshot, load_history_snapshot,
                              parse_book_summary, parse_instrument_name)

DATA = Path(__file__).parent / "data"
CHAIN = DATA / "deribit_btc_options_snapshot.json"
HIST = DATA / "deribit_btc_daily_history.json"


def test_snapshots_carry_provenance():
    for f in (CHAIN, HIST):
        prov = json.loads(f.read_text())["provenance"]
        assert "Deribit" in prov["source"] and prov["retrieved_utc"].endswith("Z")


def test_parse_instrument_name():
    cur, expiry, strike, is_call = parse_instrument_name("BTC-27NOV26-73000-P")
    assert (cur, strike, is_call) == ("BTC", 73000.0, False)
    assert (expiry.year, expiry.month, expiry.day, expiry.hour) == (2026, 11, 27, 8)
    assert parse_instrument_name("BTC-1NOV26-90000-C")[1].day == 1


@pytest.mark.parametrize("bad", ["BTC-PERPETUAL", "BTC-27XXX26-1-C", "BTC-27NOV26-1-X", ""])
def test_parse_instrument_name_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_instrument_name(bad)


def test_prices_are_converted_from_coin_to_usd():
    row = {"instrument_name": "BTC-27NOV26-73000-P", "bid_price": 0.01, "ask_price": 0.011,
           "mark_price": 0.0105, "mark_iv": 40.0, "underlying_price": 80000.0,
           "estimated_delivery_price": 79900.0, "open_interest": 1.0, "volume": 0.0,
           "creation_timestamp": 1_793_305_008_606}
    q = parse_book_summary([row]).quotes[0]
    assert q.bid == pytest.approx(800.0) and q.ask == pytest.approx(880.0)
    assert q.mark_iv == pytest.approx(0.40)


def test_one_sided_and_empty_quotes_are_not_invented():
    row = {"instrument_name": "BTC-27NOV26-73000-P", "bid_price": None, "ask_price": 0.011,
           "mark_price": 0.0105, "mark_iv": 40.0, "underlying_price": 80000.0,
           "open_interest": 0, "creation_timestamp": 1_793_305_008_606}
    q = parse_book_summary([row]).quotes[0]
    assert q.bid is None and q.ask == pytest.approx(880.0)


def test_empty_book_raises():
    with pytest.raises(ValueError):
        parse_book_summary([])


@pytest.fixture(scope="module")
def analysis():
    return analyze_chain(load_chain_snapshot(CHAIN))


def test_counts_add_up(analysis):
    c = analysis["counts"]
    assert c["total"] == 320
    assert c["total"] == (c["too_close_to_expiry"] + c["no_quote"] + c["one_sided"] + c["two_sided"])
    assert c["two_sided"] == c["iv_solved"] + c["iv_failed"]
    assert c["iv_solved"] > 100
    assert len(analysis["rows"]) == c["total"] - c["too_close_to_expiry"]


def test_engine_reproduces_exchange_mark_price_at_mark_iv(analysis):
    # Model price at Deribit's own mark IV must land on Deribit's mark price,
    # within the rounding of the quoted mark IV (two decimals of a vol point)
    # and of the mark price itself.
    checked = 0
    for r in analysis["rows"]:
        if r["model_at_mark_iv"] is None or r["mark"] is None or r["open_interest"] < 10:
            continue
        tol = 0.02 * r["mark"] + 0.5
        assert abs(r["model_at_mark_iv"] - r["mark"]) < tol, r["name"]
        checked += 1
    assert checked > 50


def test_solved_iv_round_trips_to_mid(analysis):
    from vanna.pricing.black_scholes import price
    for r in analysis["rows"]:
        if r["iv_mid"]:
            p = price(r["forward"], r["strike"], r["T"], 0.0, r["iv_mid"], r["is_call"])
            assert p == pytest.approx(r["mid"], rel=1e-6, abs=1e-6)


def test_greeks_signs_and_scaling(analysis):
    rows = [r for r in analysis["rows"] if r["greeks"]]
    assert rows
    for r in rows:
        g = r["greeks"]
        assert 0 <= g["delta"] <= 1 if r["is_call"] else -1 <= g["delta"] <= 0
        assert g["gamma"] >= 0 and g["vega"] >= 0
    # Vanna of a call and put with the same strike/expiry are equal (parity).
    by = {}
    for r in rows:
        by.setdefault((r["expiry"], r["strike"]), {})[r["is_call"]] = r
    pairs = [v for v in by.values() if len(v) == 2]
    assert pairs
    for v in pairs:
        # Both sides solve to (nearly) the same IV only if quotes are consistent,
        # so compare loosely and only where the two IVs agree to a vol point.
        if abs(v[True]["iv_mid"] - v[False]["iv_mid"]) < 0.01:
            assert v[True]["greeks"]["vanna"] == pytest.approx(v[False]["greeks"]["vanna"], rel=0.2, abs=1e-3)


def test_expiry_filter():
    out = analyze_chain(load_chain_snapshot(CHAIN), expiry="25DEC26")
    assert out["counts"]["total"] > 0
    assert {r["expiry"] for r in out["rows"]} == {"25DEC26"}


def test_history_snapshot_is_aligned_and_real_looking():
    h = load_history_snapshot(HIST)
    assert len(h.dates) == len(h.closes) == len(h.iv) > 300
    assert list(h.dates) == sorted(set(h.dates))
    assert all(c > 1000 for c in h.closes) and all(0.05 < v < 3 for v in h.iv)


def test_backtest_on_supplied_paths_is_deterministic():
    h = load_history_snapshot(HIST)
    kw = dict(strategy="iron_condor", s0=h.closes[0], iv0=h.iv[0], r=0.0, mu=0.0,
              entry_dte=30, exit_dte=10, n_trades=1000,
              spot_path=list(h.closes), iv_path=list(h.iv))
    a, b = run_backtest(**kw), run_backtest(**kw)
    assert a.equity_curve == b.equity_curve and 10 < len(a.trades) < 40
    for t in a.trades:
        assert t.entry_spot in h.closes


def test_supplied_paths_validation():
    with pytest.raises(ValueError):
        run_backtest("iron_condor", 100, 0.2, 0.0, 0.0, 30, 10, 5, spot_path=[100.0] * 50)
    with pytest.raises(ValueError):
        run_backtest("iron_condor", 100, 0.2, 0.0, 0.0, 30, 10, 5,
                     spot_path=[100.0] * 50, iv_path=[0.2] * 49)
    with pytest.raises(ValueError):
        run_backtest("iron_condor", 100, 0.2, 0.0, 0.0, 30, 10, 5,
                     spot_path=[100.0] * 20, iv_path=[0.2] * 20)
    with pytest.raises(ValueError):
        run_backtest("iron_condor", 100, 0.2, 0.0, 0.0, 30, 10, 5,
                     spot_path=[100.0] * 49 + [-1.0], iv_path=[0.2] * 50)
