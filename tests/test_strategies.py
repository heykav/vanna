from vanna.backtest.strategies import STRATEGIES

SPOT, R, IV, DTE = 100.0, 0.03, 0.22, 30


def test_iron_condor_has_four_legs_with_correct_structure():
    legs = STRATEGIES["iron_condor"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    assert len(legs) == 4
    calls = [l for l in legs if l.is_call]
    puts = [l for l in legs if not l.is_call]
    assert len(calls) == 2 and len(puts) == 2

    short_call = next(l for l in calls if l.quantity < 0)
    long_call = next(l for l in calls if l.quantity > 0)
    short_put = next(l for l in puts if l.quantity < 0)
    long_put = next(l for l in puts if l.quantity > 0)

    # The classic iron condor shape: short strikes closer to spot than the
    # long "wing" strikes that cap risk, on both sides.
    assert long_call.strike > short_call.strike > SPOT
    assert long_put.strike < short_put.strike < SPOT


def test_long_call_spread_long_leg_more_itm_than_short_leg():
    legs = STRATEGIES["long_call_spread"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    long_leg = next(l for l in legs if l.quantity > 0)
    short_leg = next(l for l in legs if l.quantity < 0)
    assert long_leg.strike < short_leg.strike  # bought the closer/cheaper-to-ITM strike


def test_straddle_legs_share_the_same_strike():
    legs = STRATEGIES["long_straddle"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    strikes = {l.strike for l in legs}
    assert len(strikes) == 1
    assert {l.is_call for l in legs} == {True, False}


def test_short_straddle_is_the_mirror_of_long_straddle():
    long_legs = STRATEGIES["long_straddle"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    short_legs = STRATEGIES["short_straddle"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    assert {(l.is_call, l.strike) for l in long_legs} == {(l.is_call, l.strike) for l in short_legs}
    assert all(l.quantity == 1 for l in long_legs)
    assert all(l.quantity == -1 for l in short_legs)


def test_every_registered_strategy_produces_at_least_one_leg():
    for name, fn in STRATEGIES.items():
        legs = fn(spot=SPOT, r=R, iv=IV, dte_days=DTE)
        assert len(legs) >= 1, f"{name} produced no legs"
        assert all(l.dte_days == DTE for l in legs), f"{name} leg DTE mismatch"
