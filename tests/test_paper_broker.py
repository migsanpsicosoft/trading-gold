"""Tests del paper broker interno (contabilidad de la cuenta virtual)."""

import pytest

import gold_bot.execution.paper_broker as pb
from gold_bot.data.db import connect


@pytest.fixture
def paper(monkeypatch, tmp_path):
    """PaperBroker sobre una base temporal con precios conocidos."""
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    conn.execute("INSERT INTO bars (symbol, date, open, high, low, close) "
                 "VALUES ('XAU', '2026-07-04', 4000, 4000, 4000, 4000)")
    conn.execute("INSERT INTO bars (symbol, date, open, high, low, close) "
                 "VALUES ('EUR', '2026-07-04', 1.25, 1.25, 1.25, 1.25)")
    conn.execute(
        "INSERT INTO intraday_bars (symbol, ts, bid_close, ask_close) "
        "VALUES ('XAU', '2026-07-04T20:45:00', 3999.8, 4000.2)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(pb, "connect", lambda: connect(db_path))
    return pb.PaperBroker()


def test_initial_state(paper):
    state = paper.state()
    assert state.balance == 50_000.0
    assert state.held_units == 0
    assert state.currency == "EUR"
    assert state.mid == 4000.0
    assert state.ask - state.bid == pytest.approx(0.4)


def test_buy_pays_ask_and_marks_to_market(paper):
    paper.market_order(5)  # compra 5 oz al ask 4000.2
    state = paper.state()
    assert state.held_units == 5
    # coste: 5 × 4000.2 / 1.25 = 16000.8€; posición vale 5 × 4000 / 1.25 = 16000€
    # equity = 50000 − 16000.8 + 16000 = 49999.2 (pagó medio spread × 5)
    assert state.balance == pytest.approx(49_999.2)


def test_round_trip_costs_full_spread(paper):
    paper.market_order(5)
    paper.market_order(-5)
    state = paper.state()
    assert state.held_units == 0
    # ida y vuelta: spread completo 0.4$ × 5 oz / 1.25 = 1.6€
    assert state.balance == pytest.approx(50_000 - 1.6)


def test_position_persists_between_instances(paper, monkeypatch):
    paper.market_order(3)
    fresh = pb.PaperBroker()  # nueva instancia, misma base
    assert fresh.state().held_units == 3
