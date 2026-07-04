"""Tests del formato del informe diario de Telegram."""

from gold_bot.execution.notify import format_daily_report


def test_report_buy_order():
    msg = format_daily_report(
        {"signal_date": "2026-07-03", "exposure": 0.42, "target_units": 6,
         "order_units": 2, "dry_run": False},
        balance=50_000.0, currency="EUR", regime_label="calma",
        gates_on=5, gates_total=7, brake=1.0,
    )
    assert "COMPRA 2 oz" in msg
    assert "+42.0%" in msg
    assert "calma" in msg
    assert "50,000.00 EUR" in msg
    assert "dry-run" not in msg


def test_report_no_change_dry_run():
    msg = format_daily_report(
        {"signal_date": "2026-07-03", "exposure": -0.1, "target_units": -1,
         "order_units": 0, "dry_run": True},
        balance=50_000.0, currency="EUR", regime_label="turbulencia",
        gates_on=3, gates_total=7, brake=0.22,
    )
    assert "sin cambios" in msg
    assert "dry-run" in msg
    assert "×0.22" in msg


def test_report_sell_order():
    msg = format_daily_report(
        {"signal_date": "2026-07-03", "exposure": -0.5, "target_units": -7,
         "order_units": -4, "dry_run": False},
        balance=48_000.0, currency="EUR", regime_label="transición",
        gates_on=6, gates_total=7, brake=0.8,
    )
    assert "VENTA 4 oz" in msg
