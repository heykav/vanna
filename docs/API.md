# API reference

Signatures below are checked against the source by `tests/test_api_docs.py`. See `examples/` for runnable scripts and [benchmarks](benchmarks.md) for accuracy and speed. Install name `vanna-greeks`, import name `vanna`.

## Pricing: Black-Scholes-Merton

Closed-form European pricing with a continuous dividend yield `q` (default 0). Conventions: `T` in years, `r` and `q` continuously compounded, `sigma` annualised, `is_call=True` for calls.

#### `vanna.pricing.black_scholes.price(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0) -> float`

European option price. Raises `ValueError` for non-finite or non-positive S, K, T, sigma.

#### `vanna.pricing.black_scholes.greeks(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0) -> vanna.pricing.black_scholes.Greeks`

Price and all Greeks in one call, returned as a `Greeks`.

#### `vanna.pricing.black_scholes.Greeks(price: float, delta: float, gamma: float, vega: float, theta: float, rho: float, vanna: float, volga: float)`

Frozen dataclass. `vega` and `rho` are per 1.00 change (divide by 100 for per 1%/1 vol point); `theta` is per year of calendar time (divide by 365 for per day); `vanna` is d(delta)/d(sigma); `volga` is d(vega)/d(sigma).

#### `vanna.pricing.black_scholes.validate_option_inputs(S: float, K: float, T: float, sigma: float, r: float | None = None, q: float | None = None) -> None`

Raises a specific `ValueError` for the first invalid input. Used by every pricing entry point.

## Pricing: binomial tree (American)

Cox-Ross-Rubinstein tree with early exercise. Greeks come from the first layers of the same tree; `theta` is per year. `steps` trades accuracy for time (see [benchmarks](benchmarks.md)).

#### `vanna.pricing.binomial.price_binomial(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0, steps: int = 200, american: bool = True) -> float`

Tree price. `american=False` gives the European tree, which converges to Black-Scholes-Merton. Raises `ValueError` if `steps` is too coarse for the parameters (risk-neutral probability outside (0, 1)).

#### `vanna.pricing.binomial.greeks_binomial(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0, steps: int = 200, american: bool = True) -> vanna.pricing.binomial.BinomialGreeks`

Price, delta, gamma and theta from one tree. Requires `steps >= 2`.

#### `vanna.pricing.binomial.BinomialGreeks(price: float, delta: float, gamma: float, theta: float)`

Frozen dataclass returned by `greeks_binomial`.

## Pricing: implied volatility

Newton-Raphson with a bisection fallback when vega is near zero.

#### `vanna.pricing.implied_vol.implied_vol(market_price: float, S: float, K: float, T: float, r: float, is_call: bool, q: float = 0.0, initial_guess: float = 0.3, newton_tol: float = 1e-08, newton_max_iter: int = 50, bisection_bounds: tuple[float, float] = (0.0001, 5.0), bisection_tol: float = 1e-10, bisection_max_iter: int = 100) -> float`

Solve for sigma given a market price. Raises `ImpliedVolError` if the price is below the discounted no-arbitrage floor or no sigma in `bisection_bounds` reproduces it. `bisection_tol` is a tolerance on the width of the sigma bracket.

#### `vanna.pricing.implied_vol.ImpliedVolError`

Subclass of `ValueError`.

## Backtesting

Model-driven: the underlying follows GBM and a mean-reverting IV path, and every option is priced from Black-Scholes-Merton. One trade is open at a time. P&L is per share.

#### `vanna.backtest.engine.run_backtest(strategy: str, s0: float, iv0: float, r: float, mu: float, entry_dte: int, exit_dte: int, n_trades: int, seed: int = 0, vol_of_vol: float = 0.01, iv_mean_reversion: float = 0.05, q: float = 0.0, spot_path=None, iv_path=None, **strategy_params) -> vanna.backtest.engine.BacktestResult`

Run a sequential backtest. Extra keyword arguments (for example `delta=0.25`) are passed to the strategy function. Pass `q` for a continuous dividend yield. Pass `spot_path` and `iv_path` together (equal-length daily sequences) to run on supplied data, for example the real history from `vanna.marketdata`, instead of the simulated paths; `n_trades` then caps the number of trades and trading stops when the data ends. Options are still priced by the model on those inputs. Raises `ValueError` on invalid input.

#### `vanna.backtest.engine.BacktestResult(equity_curve: list[float], trades: list[vanna.backtest.engine.Trade] = <factory>)`

`equity_curve` starts at 0.0 and has one point per trade; `trades` is the list of `Trade`; `total_pnl` is a property.

#### `vanna.backtest.engine.Trade(entry_day: int, exit_day: int, legs: list[vanna.backtest.strategies.Leg], entry_spot: float, entry_iv: float, entry_value: float, exit_value: float, pnl: float, attribution: vanna.backtest.attribution.AttributionResult)`

One completed trade with its legs, entry/exit values, `pnl` and a summed `AttributionResult`.

#### `vanna.backtest.metrics.summarize(result: vanna.backtest.engine.BacktestResult) -> vanna.backtest.metrics.PerformanceSummary`

Win rate, profit factor, total P&L, max drawdown, average P&L per trade, as a `PerformanceSummary`.

#### `vanna.backtest.metrics.PerformanceSummary(n_trades: int, win_rate: float, profit_factor: float, total_pnl: float, max_drawdown: float, avg_pnl: float)`

Frozen dataclass returned by `summarize`.

#### `vanna.backtest.attribution.attribute_pnl(legs: list[vanna.backtest.strategies.Leg], r: float, s0: float, iv0: float, elapsed0: int, s1: float, iv1: float, elapsed1: int, q: float = 0.0) -> vanna.backtest.attribution.AttributionResult`

Greek attribution of the P&L between two states of a position, from a second-order Taylor expansion evaluated with start-of-period Greeks. `residual` is the unexplained remainder; it is never folded into a named term.

#### `vanna.backtest.attribution.AttributionResult(total_pnl: float, delta_pnl: float, gamma_pnl: float, theta_pnl: float, vega_pnl: float, vanna_pnl: float, volga_pnl: float, residual: float, dividend_pnl: float = 0.0)`

Frozen dataclass. `total_pnl = delta + gamma + theta + vega + vanna + volga + dividend + residual`. `dividend_pnl` is dividend income on stock legs and is 0.0 when `q == 0`.

#### `vanna.backtest.attribution.position_value(legs: list[vanna.backtest.strategies.Leg], spot: float, r: float, iv: float, elapsed_days: int, q: float = 0.0) -> float`

Mark-to-model value of a list of legs after `elapsed_days`.

#### `vanna.backtest.strategies.Leg(is_call: bool, strike: float, quantity: int, dte_days: int, is_stock: bool = False)`

One leg. `quantity` is +1 long / -1 short per share; `is_stock=True` makes it a share of the underlying (delta 1).

#### `vanna.backtest.chain.simulate_gbm_path(s0: float, mu: float, sigma: float, days: int, seed: int) -> numpy.ndarray`

Daily-close GBM path of length `days + 1`, deterministic in `seed`.

#### `vanna.backtest.chain.simulate_iv_path(iv0: float, vol_of_vol: float, mean_reversion: float, days: int, seed: int, floor: float = 0.03) -> numpy.ndarray`

Mean-reverting daily IV path, floored at `floor`.

#### `vanna.backtest.chain.price_leg(spot: float, strike: float, dte_days: int, r: float, iv: float, is_call: bool, q: float = 0.0) -> float`

Black-Scholes-Merton price of one option leg with `dte_days` calendar days (converted to years with 252 trading days per year); intrinsic value at or past expiry.

#### `vanna.backtest.chain.leg_greeks(spot: float, strike: float, dte_days: int, r: float, iv: float, is_call: bool, q: float = 0.0)`

Greeks of one leg, or `None` at or past expiry.

#### `vanna.backtest.chain.nearest_strike(spot: float, target_delta: float, dte_days: int, r: float, iv: float, is_call: bool, strike_step: float = 1.0, q: float = 0.0) -> float`

Strike whose Black-Scholes delta is closest to `target_delta` (in absolute value), floored at one `strike_step`.

#### `vanna.backtest.payoff.payoff_curve(legs, r: float, iv: float, entry_spot: float, spots, q: float = 0.0)`

P&L at expiry for each spot in `spots`, net of entry premium.

### Strategies

Strategy functions take `(spot, r, iv, dte_days, ...)` and return a list of `Leg`; look them up in `vanna.backtest.strategies.STRATEGIES`.

Available: `covered_call`, `iron_condor`, `long_call`, `long_call_spread`, `long_put`, `long_straddle`, `short_call`, `short_call_spread`, `short_put`, `short_straddle`.

Strike-picking strategies accept delta targets as keyword arguments (`delta`, `long_delta`, `short_delta`, `wing_delta`, `body_delta`) and `q`. `covered_call` is one share plus one short OTM call.

## Market data: Deribit public API

Standard library only, no API key. Source: Deribit's public, unauthenticated endpoints (`www.deribit.com/api/v2/public/`). The data is a delayed REST snapshot (one request per call), quotes can be stale or one-sided, and the data belongs to Deribit. Deribit quotes option prices in the underlying coin; the loader converts to USD with each expiry's `underlying_price`, and pricing with `S = underlying_price`, `r = 0` reproduces Deribit's own mark IV. Crypto options only (BTC, ETH), European. See `examples/real_price_backtest.py` and the live-chain tab of the web demo.

#### `vanna.marketdata.deribit.fetch_chain(currency: str = 'BTC', timeout: float = 20.0) -> vanna.marketdata.deribit.Chain`

Download the whole public option book for `currency` in one request.

#### `vanna.marketdata.deribit.parse_book_summary(result: Iterable[dict]) -> vanna.marketdata.deribit.Chain`

Build a `Chain` from the `result` list of Deribit's `get_book_summary_by_currency`. Prices are converted from coin to USD. Missing bids or asks stay `None`.

#### `vanna.marketdata.deribit.load_chain_snapshot(path: str | pathlib.Path) -> vanna.marketdata.deribit.Chain`

Load a saved snapshot file (`{"provenance": ..., "result": [...]}`), as committed in `tests/data/`.

#### `vanna.marketdata.deribit.analyze_chain(chain: vanna.marketdata.deribit.Chain, r: float = 0.0, min_days: float = 0.5, expiry: str | None = None) -> dict`

Price every quote with vanna's own engine and return `{as_of, source, counts, rows}`. Per row: implied vol solved from the market mid, the model price at Deribit's mark IV, and Greeks (including vanna and volga) at the solved IV, with vega and vanna per vol point. `counts` assigns every quote to exactly one bucket: too close to expiry, no quote, one-sided, two-sided; two-sided quotes are then split into IV solved or failed.

#### `vanna.marketdata.deribit.parse_instrument_name(name: str) -> tuple[str, datetime.datetime, float, bool]`

Split a name such as `BTC-27NOV26-73000-P` into currency, expiry (08:00 UTC), strike and call flag. Raises `ValueError` otherwise.

#### `vanna.marketdata.deribit.fetch_history(currency: str = 'BTC', days: int = 365, timeout: float = 20.0, end_ms: int | None = None) -> vanna.marketdata.deribit.PriceHistory`

Daily closes of the `<currency>-PERPETUAL` future and the DVOL implied-volatility index (two requests), aligned by UTC day. The perpetual is a futures price, not spot, and DVOL is a 30-day index with one vol for all strikes.

#### `vanna.marketdata.deribit.parse_history(chart: dict, dvol: dict, currency: str = 'BTC') -> vanna.marketdata.deribit.PriceHistory`

Align Deribit's `get_tradingview_chart_data` and `get_volatility_index_data` responses into a `PriceHistory`.

#### `vanna.marketdata.deribit.load_history_snapshot(path: str | pathlib.Path) -> vanna.marketdata.deribit.PriceHistory`

Load the saved history snapshot from `tests/data/`.

#### `vanna.marketdata.deribit.OptionQuote(name: str, expiry: datetime.datetime, strike: float, is_call: bool, forward: float, bid: float | None, ask: float | None, mark: float | None, mark_iv: float | None, open_interest: float, volume: float)`

One option quote, prices in USD.

#### `vanna.marketdata.deribit.Chain(currency: str, as_of: datetime.datetime, index_price: float | None, quotes: tuple[vanna.marketdata.deribit.OptionQuote, ...], source: str = 'Deribit public API (www.deribit.com), delayed REST snapshot, unauthenticated')`

A set of quotes with its timestamp and source.

#### `vanna.marketdata.deribit.PriceHistory(currency: str, dates: tuple[str, ...], closes: tuple[float, ...], iv: tuple[float, ...], source: str = 'Deribit public API (www.deribit.com), delayed REST snapshot, unauthenticated')`

Aligned daily closes and IV (decimal) with dates.

## Command line

```
vanna STRATEGY [--spot S] [--iv IV] [--rate R] [--div-yield Q] [--drift MU]
            [--entry-dte N] [--exit-dte N] [--trades N] [--seed N]
```

Prints summary statistics and the Greek attribution of the most recent trade. Exit code 1 on invalid parameters.
