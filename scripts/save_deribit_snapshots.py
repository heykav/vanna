"""Re-capture the committed Deribit snapshots in tests/data/.

Usage: python scripts/save_deribit_snapshots.py
Needs network access to www.deribit.com (public endpoints, no key). The
snapshots are trimmed to the fields vanna reads and to a few expiries so
they stay small; the provenance block records when and how they were taken.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vanna.marketdata import deribit as d  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "data"
KEEP_EXPIRIES = {"27NOV26", "25DEC26", "26MAR27"}
FIELDS = ("instrument_name", "bid_price", "ask_price", "mark_price", "mark_iv",
          "underlying_price", "estimated_delivery_price", "open_interest", "volume",
          "creation_timestamp")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    rows = d._get_json("get_book_summary_by_currency", {"currency": "BTC", "kind": "option"}, 30)
    kept = [{k: r.get(k) for k in FIELDS} for r in rows
            if r["instrument_name"].split("-")[1] in KEEP_EXPIRIES]
    prov = {
        "source": "Deribit public API, unauthenticated",
        "endpoint": d.BASE_URL + "get_book_summary_by_currency?currency=BTC&kind=option",
        "retrieved_utc": now_iso(),
        "trimmed_to": f"expiries {sorted(KEEP_EXPIRIES)} and the fields {list(FIELDS)}; "
                      f"{len(kept)} of {len(rows)} instruments",
        "note": "Prices are in BTC as quoted by Deribit. Data belongs to Deribit; kept here "
                "only as a small test fixture.",
    }
    (OUT / "deribit_btc_options_snapshot.json").write_text(
        json.dumps({"provenance": prov, "result": kept}, indent=1) + "\n")

    end = int(time.time() * 1000)
    start = end - 400 * 86_400_000
    chart = d._get_json("get_tradingview_chart_data", {
        "instrument_name": "BTC-PERPETUAL", "start_timestamp": start,
        "end_timestamp": end, "resolution": "1D"}, 30)
    dvol = d._get_json("get_volatility_index_data", {
        "currency": "BTC", "start_timestamp": start, "end_timestamp": end,
        "resolution": "86400"}, 30)
    chart = {k: chart[k] for k in ("ticks", "close")}
    prov = {
        "source": "Deribit public API, unauthenticated",
        "endpoints": [d.BASE_URL + "get_tradingview_chart_data?instrument_name=BTC-PERPETUAL&resolution=1D",
                      d.BASE_URL + "get_volatility_index_data?currency=BTC&resolution=86400"],
        "retrieved_utc": now_iso(),
        "note": "Daily closes of the BTC perpetual future (not spot) and the DVOL 30-day implied "
                "volatility index (in vol points). Data belongs to Deribit.",
    }
    (OUT / "deribit_btc_daily_history.json").write_text(
        json.dumps({"provenance": prov, "currency": "BTC", "chart": chart, "dvol": dvol}) + "\n")


if __name__ == "__main__":
    main()
