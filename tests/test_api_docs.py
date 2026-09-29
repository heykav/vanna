"""docs/API.md must match the real signatures (headings are `module.name(sig)`)."""
import importlib
import inspect
import re
from pathlib import Path

import pytest

API = Path(__file__).resolve().parent.parent / "docs" / "API.md"
HEADINGS = re.findall(r"^#### `(.+)`$", API.read_text(encoding="utf-8"), flags=re.M)


def _render(obj):
    if inspect.isclass(obj) and issubclass(obj, BaseException):
        return ""
    sig = inspect.signature(obj, eval_str=True)
    if inspect.isclass(obj):
        sig = sig.replace(return_annotation=inspect.Signature.empty)
    return str(sig)


def test_api_reference_is_not_empty():
    assert len(HEADINGS) >= 20


@pytest.mark.parametrize("heading", HEADINGS)
def test_documented_signature_matches_source(heading):
    qualified = heading.split("(", 1)[0]
    module, name = qualified.rsplit(".", 1)
    obj = getattr(importlib.import_module(module), name)
    assert heading == qualified + _render(obj)


def test_documented_docstring_facts():
    text = API.read_text(encoding="utf-8")
    from vanna.backtest.strategies import STRATEGIES
    for name in STRATEGIES:
        assert f"`{name}`" in text
