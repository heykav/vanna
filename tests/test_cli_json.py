"""Public JSON contract and reconciliation with the actual simulation."""
import json
from dataclasses import replace

import pytest

from vanna.cli import main
from vanna.backtest.engine import BacktestResult, run_backtest
from vanna.backtest.serialize import attribution_to_dict


def reject_constant(value):
    raise AssertionError(f"Non-standard JSON number: {value}")


def output(capsys, *args):
    assert main(["iron_condor", "--json", *args]) == 0
    streams = capsys.readouterr()
    assert streams.err == ""
    return streams.out, json.loads(streams.out, parse_constant=reject_constant)


def test_results_reconcile_with_engine(capsys):
    _, data = output(capsys, "--trades", "3", "--seed", "123", "--div-yield", "0.02")
    result = run_backtest("iron_condor", 100, .22, .03, 0, 30, 10, 3, seed=123, q=.02)
    assert data["schema_version"] == "1.0.0"
    assert data["parameters"]["seed"] == 123
    assert data["parameters"]["dividend_yield"] == .02
    assert data["equity_curve"] == result.equity_curve
    assert data["summary"]["total_pnl"] == pytest.approx(sum(t.pnl for t in result.trades))
    for actual, trade in zip(data["trades"], result.trades, strict=True):
        assert actual["pnl"] == trade.pnl
        assert actual["attribution"] == attribution_to_dict(trade.attribution)
        attr = actual["attribution"]
        assert sum(v for k, v in attr.items() if k != "total_pnl") == pytest.approx(attr["total_pnl"])


def test_seed_determinism(capsys):
    first, a = output(capsys, "--seed", "10")
    second, _ = output(capsys, "--seed", "10")
    _, b = output(capsys, "--seed", "11")
    assert first == second
    assert a["trades"] != b["trades"]


@pytest.mark.parametrize("args", [["--spot", "-1"], ["--iv", "nan"], ["--trades", "0"], ["--exit-dte", "31"], ["--seed", "-1"]])
def test_invalid_inputs_leave_stdout_empty(capsys, args):
    assert main(["iron_condor", "--json", *args]) != 0
    streams = capsys.readouterr()
    assert streams.out == ""
    assert streams.err


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_numbers_are_null(capsys, monkeypatch, value):
    result = run_backtest("iron_condor", 100, .22, .03, 0, 30, 10, 1)
    result.trades[0].attribution = replace(result.trades[0].attribution, residual=value)
    result.equity_curve[-1] = value
    monkeypatch.setattr("vanna.cli.run_backtest", lambda **kwargs: result)
    _, data = output(capsys)
    assert data["trades"][0]["attribution"]["residual"] is None
    assert data["equity_curve"][-1] is None


def test_empty_result_error_channel(capsys, monkeypatch):
    monkeypatch.setattr("vanna.cli.run_backtest", lambda **kwargs: BacktestResult([]))
    assert main(["iron_condor", "--json"]) == 1
    streams = capsys.readouterr()
    assert streams.out == ""
    assert streams.err


def test_default_output_remains_human(capsys):
    assert main(["iron_condor"]) == 0
    streams = capsys.readouterr()
    assert "Strategy:" in streams.out
    assert "Greek attribution" in streams.out
