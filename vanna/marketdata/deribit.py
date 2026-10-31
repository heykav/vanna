"""Loader for Deribit's public, unauthenticated market data.

Source: https://www.deribit.com/api/v2/public/ (no key, no login). Deribit
publishes option book summaries (bid, ask, mark, mark IV, open interest per
instrument) and daily history for the BTC perpetual and the DVOL index.
Standard library only (urllib, json), so the same code runs under Pyodide
in the web demo, where the browser does the fetch and hands the JSON in.

Conventions this module relies on, each checked against the live book:

* Deribit option prices are quoted in the underlying coin. USD price is
  ``coin_price * underlying_price``, where ``underlying_price`` is the
  synthetic future for that expiry.
* Pricing with ``S = underlying_price``, ``r = 0``, ``q = 0`` in
  Black-Scholes (Black-76 with a forward) reproduces Deribit's own mark IV
  to within the rounding of the quoted prices.
* Options expire at 08:00 UTC on the expiry date.

Limits: the data is a point-in-time REST snapshot, not a tick feed. Quotes
can be stale or one-sided. Deribit's published API usage policy asks
clients not to poll aggressively; ``fetch_chain`` makes one request.
Nothing here is investment advice, and the data belongs to Deribit.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from vanna.pricing.black_scholes import greeks, price
from vanna.pricing.implied_vol import ImpliedVolError, implied_vol

BASE_URL = "https://www.deribit.com/api/v2/public/"
SOURCE = "Deribit public API (www.deribit.com), delayed REST snapshot, unauthenticated"
SECONDS_PER_YEAR = 365.0 * 86400.0

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


@dataclass(frozen=True)
class OptionQuote:
    """One option, with prices converted to USD."""
    name: str
    expiry: datetime
    strike: float
    is_call: bool
    forward: float          # Deribit underlying_price for this expiry
    bid: float | None       # USD
    ask: float | None       # USD
    mark: float | None      # USD
    mark_iv: float | None   # decimal, e.g. 0.40
    open_interest: float
    volume: float


@dataclass(frozen=True)
class Chain:
    currency: str
    as_of: datetime
    index_price: float | None
    quotes: tuple[OptionQuote, ...]
    source: str = SOURCE


@dataclass(frozen=True)
class PriceHistory:
    """Aligned daily closes (UTC) of the BTC perpetual and the DVOL index."""
    currency: str
    dates: tuple[str, ...]
    closes: tuple[float, ...]
    iv: tuple[float, ...]   # DVOL / 100, decimal
    source: str = SOURCE


def parse_instrument_name(name: str) -> tuple[str, datetime, float, bool]:
    """``"BTC-27NOV26-73000-P"`` -> (currency, expiry 08:00 UTC, strike, is_call)."""
    try:
        cur, exp, strike, cp = name.split("-")
        day, mon, yr = int(exp[:-5]), exp[-5:-2].upper(), int(exp[-2:])
        expiry = datetime(2000 + yr, _MONTHS[mon], day, 8, tzinfo=timezone.utc)
        if cp not in ("C", "P"):
            raise ValueError(cp)
        return cur, expiry, float(strike), cp == "C"
    except (ValueError, KeyError, IndexError) as exc:
        raise ValueError(f"not a Deribit option instrument name: {name!r}") from exc


def _num(x):
    return float(x) if isinstance(x, (int, float)) and math.isfinite(x) and x > 0 else None


def parse_book_summary(result: Iterable[dict]) -> Chain:
    """Build a Chain from the ``result`` list of ``get_book_summary_by_currency``."""
    quotes, stamps, cur = [], [], None
    for row in result:
        c, expiry, strike, is_call = parse_instrument_name(row["instrument_name"])
        cur = cur or c
        fwd = _num(row.get("underlying_price"))
        if fwd is None:
            continue
        usd = lambda coin: None if _num(coin) is None else float(coin) * fwd
        iv = _num(row.get("mark_iv"))
        quotes.append(OptionQuote(
            name=row["instrument_name"], expiry=expiry, strike=strike, is_call=is_call,
            forward=fwd, bid=usd(row.get("bid_price")), ask=usd(row.get("ask_price")),
            mark=usd(row.get("mark_price")), mark_iv=None if iv is None else iv / 100.0,
            open_interest=float(row.get("open_interest") or 0.0),
            volume=float(row.get("volume") or 0.0)))
        if row.get("creation_timestamp"):
            stamps.append(row["creation_timestamp"])
    if not quotes:
        raise ValueError("book summary contained no usable option rows")
    as_of = datetime.fromtimestamp(max(stamps) / 1000.0, tz=timezone.utc)
    idx = [r.get("estimated_delivery_price") for r in result if r.get("estimated_delivery_price")]
    return Chain(currency=cur, as_of=as_of, index_price=float(idx[0]) if idx else None,
                 quotes=tuple(quotes))


def _get_json(endpoint: str, params: dict, timeout: float) -> dict:
    url = BASE_URL + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "vanna-greeks/0.1 (+https://github.com/heykav/vanna)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    if "result" not in payload:
        raise RuntimeError(f"Deribit returned an error for {endpoint}: {payload.get('error')}")
    return payload["result"]


def fetch_chain(currency: str = "BTC", timeout: float = 20.0) -> Chain:
    """One request for the whole public option book of ``currency`` (BTC or ETH)."""
    return parse_book_summary(_get_json(
        "get_book_summary_by_currency", {"currency": currency, "kind": "option"}, timeout))


def load_chain_snapshot(path: str | Path) -> Chain:
    """Load a saved snapshot (``{"provenance": ..., "result": [...]}``)."""
    return parse_book_summary(json.loads(Path(path).read_text())["result"])


def analyze_chain(chain: Chain, r: float = 0.0, min_days: float = 0.5,
                  expiry: str | None = None) -> dict:
    """Price every quote with vanna's own engine.

    Per option: the implied vol solved from the market mid with
    ``vanna.pricing.implied_vol``, the model price at Deribit's mark IV
    (an independent check of the engine against the exchange), and the Greeks,
    including vanna and volga, at the solved IV. Greeks are per option in USD:
    vega, vanna per 1 vol point; volga per 1 vol point squared.

    Returns ``{"as_of", "source", "counts", "rows"}``. Counts always add up:
    every quote is in exactly one of the buckets.
    """
    rows, counts = [], {"total": 0, "too_close_to_expiry": 0, "no_quote": 0,
                        "one_sided": 0, "two_sided": 0, "iv_solved": 0, "iv_failed": 0}
    for q in chain.quotes:
        if expiry is not None and q.expiry.strftime("%d%b%y").lstrip("0").upper() != expiry.upper():
            continue
        counts["total"] += 1
        T = (q.expiry - chain.as_of).total_seconds() / SECONDS_PER_YEAR
        if T * 365.0 < min_days:
            counts["too_close_to_expiry"] += 1
            continue
        two = q.bid is not None and q.ask is not None and q.ask >= q.bid
        mid = 0.5 * (q.bid + q.ask) if two else None
        counts["two_sided" if two else ("one_sided" if (q.bid or q.ask) else "no_quote")] += 1
        row = {"name": q.name, "expiry": q.expiry.strftime("%d%b%y").lstrip("0").upper(),
               "strike": q.strike, "is_call": q.is_call, "T": T, "forward": q.forward,
               "bid": q.bid, "ask": q.ask, "mid": mid, "mark": q.mark,
               "mark_iv": q.mark_iv, "open_interest": q.open_interest, "two_sided": two,
               "model_at_mark_iv": None, "iv_mid": None, "greeks": None}
        if q.mark_iv:
            row["model_at_mark_iv"] = price(q.forward, q.strike, T, r, q.mark_iv, q.is_call)
        if mid is not None:
            try:
                iv = implied_vol(mid, q.forward, q.strike, T, r, q.is_call)
                g = greeks(q.forward, q.strike, T, r, iv, q.is_call)
                row["iv_mid"] = iv
                row["greeks"] = {"delta": g.delta, "gamma": g.gamma, "vega": g.vega / 100.0,
                                 "theta_day": g.theta / 365.0, "vanna": g.vanna / 100.0,
                                 "volga": g.volga / 1e4}
                counts["iv_solved"] += 1
            except (ImpliedVolError, ValueError):
                counts["iv_failed"] += 1
        rows.append(row)
    rows.sort(key=lambda x: (x["T"], x["strike"], not x["is_call"]))
    return {"as_of": chain.as_of.isoformat(), "source": chain.source,
            "currency": chain.currency, "index_price": chain.index_price,
            "counts": counts, "rows": rows}


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def parse_history(chart: dict, dvol: dict, currency: str = "BTC") -> PriceHistory:
    """Align ``get_tradingview_chart_data`` (1D) with ``get_volatility_index_data`` (1D).

    Days present in only one series are dropped, so the two paths line up.
    """
    px = {_day(t): c for t, c in zip(chart["ticks"], chart["close"])}
    vol = {_day(row[0]): row[4] / 100.0 for row in dvol["data"]}
    days = sorted(set(px) & set(vol))
    if len(days) < 2:
        raise ValueError("fewer than two overlapping days of price and DVOL history")
    return PriceHistory(currency=currency, dates=tuple(days),
                        closes=tuple(px[d] for d in days), iv=tuple(vol[d] for d in days))


def fetch_history(currency: str = "BTC", days: int = 365, timeout: float = 20.0,
                  end_ms: int | None = None) -> PriceHistory:
    """Daily closes of ``<currency>-PERPETUAL`` and the DVOL index (two requests)."""
    import time
    end = end_ms or int(time.time() * 1000)
    start = end - days * 86_400_000
    chart = _get_json("get_tradingview_chart_data", {
        "instrument_name": f"{currency}-PERPETUAL", "start_timestamp": start,
        "end_timestamp": end, "resolution": "1D"}, timeout)
    dvol = _get_json("get_volatility_index_data", {
        "currency": currency, "start_timestamp": start, "end_timestamp": end,
        "resolution": "86400"}, timeout)
    return parse_history(chart, dvol, currency)


def load_history_snapshot(path: str | Path) -> PriceHistory:
    d = json.loads(Path(path).read_text())
    return parse_history(d["chart"], d["dvol"], d.get("currency", "BTC"))
