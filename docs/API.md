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

#### `vanna.pricing.black_scholes.delta(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0) -> float`

Delta alone; identical to `greeks(...).delta` but cheaper when nothing else is needed.

## Pricing: binomial tree (American)

Binomial tree with early exercise. `method="crr"` (default) is Cox-Ross-Rubinstein; `method="lr"` is Leisen-Reimer (Peizer-Pratt method 2), which is only defined for an odd step count, so an even `steps` is rounded up by one. Greeks come from the first layers of the same tree; `theta` is per year. `steps` trades accuracy for time (see [benchmarks](benchmarks.md) for the measured error per step count of both methods).

#### `vanna.pricing.binomial.price_binomial(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0, steps: int = 200, american: bool = True, method: str = 'crr') -> float`

Tree price. `american=False` gives the European tree, which converges to Black-Scholes-Merton. Raises `ValueError` if `steps` is too coarse for the parameters (risk-neutral probability outside (0, 1)).

#### `vanna.pricing.binomial.greeks_binomial(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0, steps: int = 200, american: bool = True, method: str = 'crr') -> vanna.pricing.binomial.BinomialGreeks`

Price, delta, gamma and theta from one tree. Requires `steps >= 2`.

#### `vanna.pricing.binomial.BinomialGreeks(price: float, delta: float, gamma: float, theta: float)`

Frozen dataclass returned by `greeks_binomial`.

## Pricing: implied volatility

Safeguarded Newton-Raphson: a bracket in sigma that always contains the root is kept, and any Newton step that would leave it is replaced by a bisection step, so the iteration cannot diverge when vega is near zero. ITM prices are converted by put-call parity to the equivalent OTM price, and below the inflection point of price(sigma) the Newton step is taken on ln(price), which converges in far fewer steps in the low-vega wings. The default start is that inflection point (Manaster-Koehler, `sqrt(2|ln(F/K)|/T)`).

#### `vanna.pricing.implied_vol.implied_vol(market_price: float, S: float, K: float, T: float, r: float, is_call: bool, q: float = 0.0, initial_guess: float | None = None, newton_tol: float = 1e-08, newton_max_iter: int = 50, bisection_bounds: tuple[float, float] = (0.0001, 5.0), bisection_tol: float = 1e-10, bisection_max_iter: int = 100) -> float`

Solve for sigma given a market price. Raises `ImpliedVolError` if the price is outside the no-arbitrage bounds (below the discounted intrinsic value, equal to it, i.e. no time value, or at/above `S*exp(-qT)` for a call or `K*exp(-rT)` for a put), or if the implied vol lies outside `bisection_bounds` (the message says which side). Stops when the Newton step is below 1e-9 in sigma (that final step is applied, so the error is of order its square) with a price residual below `newton_tol`, or when the bracket is narrower than `bisection_tol`.

#### `vanna.pricing.implied_vol.no_arbitrage_bounds(S: float, K: float, T: float, r: float, is_call: bool, q: float = 0.0) -> tuple[float, float]`

`(lower, upper)` model-free bounds on a European option price used by `implied_vol`.

#### `vanna.pricing.implied_vol.ImpliedVolError`

Subclass of `ValueError`.

## Backtesting

Model-driven: the underlying follows GBM and a mean-reverting IV path, and every option is priced from Black-Scholes-Merton. One trade is open at a time. P&L is per share.

#### `vanna.backtest.engine.run_backtest(strategy: str, s0: float, iv0: float, r: float, mu: float, entry_dte: int, exit_dte: int, n_trades: int, seed: int = 0, vol_of_vol: float = 0.01, iv_mean_reversion: float = 0.05, q: float = 0.0, **strategy_params) -> vanna.backtest.engine.BacktestResult`

Run a sequential backtest. Extra keyword arguments (for example `delta=0.25`) are passed to the strategy function. Pass `q` for a continuous dividend yield. Raises `ValueError` on invalid input.

#### `vanna.backtest.engine.BacktestResult(equity_curve: list[float], trades: list[vanna.backtest.engine.Trade] = <factory>)`

`equity_curve` starts at 0.0 and has one point per trade; `trades` is the list of `Trade`; `total_pnl` is a property.

#### `vanna.backtest.engine.Trade(entry_day: int, exit_day: int, legs: list[vanna.backtest.strategies.Leg], entry_spot: float, entry_iv: float, entry_value: float, exit_value: float, pnl: float, attribution: vanna.backtest.attribution.AttributionResult)`

One completed trade with its legs, entry/exit values, `pnl` and a summed `AttributionResult`.

#### `vanna.backtest.metrics.summarize(result: vanna.backtest.engine.BacktestResult) -> vanna.backtest.metrics.PerformanceSummary`

Win rate, profit factor, total P&L, max drawdown, average P&L per trade, as a `PerformanceSummary`. Max drawdown is measured on the closed-trade equity curve (one point per trade), so a drawdown that opens and recovers within a single trade is not counted.

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

Black-Scholes-Merton price of one option leg with `dte_days` trading days to expiry (converted to years as `dte_days / 252`; the simulated path has one step per trading day); intrinsic value at or past expiry.

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

## Command line

```
vanna STRATEGY [--spot S] [--iv IV] [--rate R] [--div-yield Q] [--drift MU]
            [--entry-dte N] [--exit-dte N] [--trades N] [--seed N]
```

Prints summary statistics and the Greek attribution of the most recent trade. Exit code 1 on invalid parameters.
