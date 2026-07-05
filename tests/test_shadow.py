"""Tests de la cartera sombra top10."""

from types import SimpleNamespace

import pandas as pd

from gold_bot.risk.multi_asset import TOP_CELLS, top_cells_exposures


def fake_book(positions: dict[str, list[float]]):
    idx = pd.bdate_range("2026-01-01", periods=len(next(iter(positions.values()))))
    return SimpleNamespace(
        positions={k: pd.Series(v, index=idx) for k, v in positions.items()}
    )


def test_top_cells_equal_weight():
    books = {
        "SPX": fake_book({"cot_extreme": [0, 1.0], "monthly_seasonality": [0, 1.0],
                          "vix_structure": [0, -1.0]}),
        "JPY": fake_book({"fx_carry": [0, 1.0], "ts_momentum": [0, 1.0]}),
    }
    exp = top_cells_exposures(books)
    # SPX: (1 + 1 - 1)/10 = 0.1 ; JPY: (1 + 1)/10 = 0.2
    assert exp["SPX"] == 0.1
    assert exp["JPY"] == 0.2


def test_top_cells_missing_books_are_skipped():
    exp = top_cells_exposures({})
    assert exp == {}


def test_top_cells_are_ten_and_not_excluded():
    from gold_bot.risk.multi_asset import CRIBA_EXCLUDED

    assert len(TOP_CELLS) == 10
    assert not (set(TOP_CELLS) & CRIBA_EXCLUDED)  # coherencia con la criba
