"""Tests de la lógica de decisión del runner diario."""

from gold_bot.execution.broker import BrokerState
from gold_bot.execution.daily_run import decide_order


def make_state(balance=50_000.0, currency="EUR", held=0.0,
               bid=4000.0, ask=4001.0, eur_usd=1.10) -> BrokerState:
    return BrokerState(balance=balance, currency=currency, held_units=held,
                       bid=bid, ask=ask, eur_usd=eur_usd)


def test_target_converts_eur_balance():
    # 50k€ × 1.10 = 55k$ ; exposición 0.5 → 27.5k$ / 4000.5$ ≈ 7 oz
    target, order = decide_order(make_state(), exposure=0.5)
    assert target == 7
    assert order == 7


def test_order_is_the_difference():
    target, order = decide_order(make_state(held=4.0), exposure=0.5)
    assert target == 7
    assert order == 3


def test_small_delta_does_not_trade():
    # objetivo 7, tenemos 7 → orden 0 (y deltas < 1 oz tampoco operan)
    _, order = decide_order(make_state(held=7.0), exposure=0.5)
    assert order == 0


def test_short_exposure():
    target, order = decide_order(make_state(held=2.0), exposure=-0.3)
    assert target == -4  # -0.3 × 55k / 4000.5 ≈ -4.1 → -4
    assert order == -6


def test_usd_account_skips_fx():
    state = make_state(balance=55_000.0, currency="USD", eur_usd=None)
    target, _ = decide_order(state, exposure=0.5)
    assert target == 7


def test_zero_exposure_flattens():
    target, order = decide_order(make_state(held=-5.0), exposure=0.0)
    assert target == 0
    assert order == 5
