"""Run every script in examples/ so they cannot rot."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*.py"))

EXPECTED = {
    "price_and_greeks.py": "early-exercise premium",
    "implied_vol.py": "rejected as expected",
    "covered_call_backtest.py": "Greek attribution summed",
    "dividend_yield.py": "put-call parity residual",
}


def test_all_examples_are_covered():
    assert {p.name for p in EXAMPLES} == set(EXPECTED)


@pytest.mark.parametrize("script", EXAMPLES, ids=lambda p: p.name)
def test_example_runs(script):
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          timeout=120, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert EXPECTED[script.name] in proc.stdout
