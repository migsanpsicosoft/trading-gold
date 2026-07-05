"""Runner diario de paper trading (Fase 7).

El loop de producción, pensado para correr una vez al día tras el
cierre de NY (Task Scheduler de Windows):

  1. Actualiza los datos (incremental, lo de siempre).
  2. Recalcula la cartera walk-forward → exposición objetivo de HOY.
  3. Pregunta al broker balance, precio y posición abierta.
  4. Ordena la DIFERENCIA (redondeada a onzas enteras, mínimo 1).
  5. Lo registra TODO en live_log — la página Live compara esta
     trayectoria contra el backtest teórico.

Uso:  python -m gold_bot.execution.daily_run [--dry-run]
      --dry-run: calcula y registra la decisión pero NO envía la orden.

La lógica de decisión (decide_order) es pura y está testeada; la red
(broker, datos) queda en los bordes.
"""

import sys
from datetime import UTC, datetime

from gold_bot.data.db import connect
from gold_bot.data.download import update_all
from gold_bot.data.intraday import INTRADAY_SYMBOLS, has_intraday_data, update_intraday
from gold_bot.execution.broker import BrokerState
from gold_bot.execution.notify import format_daily_report, send_telegram
from gold_bot.meta_model.pipeline import load_meta_inputs
from gold_bot.regime.hmm import REGIME_LABELS
from gold_bot.risk.gating import current_gate_report
from gold_bot.risk.portfolio import build_portfolio
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

MIN_ORDER_UNITS = 1  # OANDA opera XAU_USD en onzas enteras


def decide_order(state: BrokerState, exposure: float) -> tuple[int, int]:
    """(target_units, order_units) según el estado del broker.

    exposure: fracción de la equity a tener en XAU (con signo).
    La cuenta puede ser EUR: el balance se convierte a USD para
    dimensionar contra el precio del oro en USD.
    """
    balance_usd = state.balance * (state.eur_usd or 1.0)
    target = round(exposure * balance_usd / state.mid)
    order = target - round(state.held_units)
    if abs(order) < MIN_ORDER_UNITS:
        order = 0
    return int(target), int(order)


def run(dry_run: bool = False) -> dict:
    started = datetime.now(UTC)
    log.info("runner_inicio", dry_run=dry_run)

    # 1) datos al día (incremental)
    conn = connect()
    try:
        update_all(conn)
        for symbol in INTRADAY_SYMBOLS:
            if has_intraday_data(conn, symbol):
                update_intraday(conn, symbol)
    finally:
        conn.close()

    # 2) exposición objetivo del sistema (todo walk-forward)
    inputs = load_meta_inputs()
    portfolio = build_portfolio(inputs)
    exposure = float(portfolio["net_exposure"].dropna().iloc[-1])
    signal_date = portfolio["net_exposure"].dropna().index[-1].date().isoformat()

    # 3) estado del broker y decisión (OANDA si hay credenciales;
    #    si no, el paper broker interno — sin broker externo ni KYC)
    from gold_bot.execution.paper_broker import get_broker

    broker = get_broker()
    state = broker.state()
    target, order = decide_order(state, exposure)
    log.info("decision", fecha_senal=signal_date, exposicion=round(exposure, 4),
             balance=state.balance, divisa=state.currency,
             posicion=state.held_units, objetivo=target, orden=order)

    # 4) ejecutar
    if order != 0 and not dry_run:
        broker.market_order(order)

    # 5) registrar
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO live_log (ts, exposure, price, balance, "
            "currency, held_units, target_units, order_units, dry_run) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (started.isoformat(), exposure, state.mid, state.balance,
             state.currency, state.held_units, target,
             order if not dry_run else 0, int(dry_run)),
        )
        conn.commit()
    finally:
        conn.close()

    result = {"signal_date": signal_date, "exposure": exposure,
              "target_units": target, "order_units": order, "dry_run": dry_run}

    # 6) informe por Telegram con TODAS las señales del libro
    regime_now = int(inputs.regimes["regime"].iloc[-1])
    nets = dict(inputs.daily_net)
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        nets[name] = net_daily
    gates = current_gate_report(nets, inputs.regimes["regime"])
    gate_by_name = {g["strategy"]: g["gate_on"] for g in gates}
    weights_now = portfolio["weights"].iloc[-1]
    signals = []
    for name, positions in inputs.daily_positions.items():
        last_pos = positions.dropna()
        signals.append({
            "name": name,
            "position": float(last_pos.iloc[-1]) if len(last_pos) else 0.0,
            "gate_on": bool(gate_by_name.get(name, True)),
            "weight": float(weights_now.get(name, 0.0)),
        })
    for name, (pos_daily, _net) in inputs.intraday_results.items():
        last_pos = pos_daily.dropna()
        signals.append({
            "name": name,
            "position": float(last_pos.iloc[-1]) if len(last_pos) else 0.0,
            "gate_on": bool(gate_by_name.get(name, True)),
            "weight": float(weights_now.get(name, 0.0)),
        })
    send_telegram(format_daily_report(
        result, balance=state.balance, currency=state.currency,
        regime_label=REGIME_LABELS[regime_now],
        gates_on=sum(g["gate_on"] for g in gates), gates_total=len(gates),
        brake=float(portfolio["brake"].iloc[-1]),
        signals=signals,
    ))
    return result


def run_shadow_multi() -> None:
    """Libros sombra: exposiciones registradas SIN ordenar nada.

    Dos carteras: 'multi_full' (los 9 libros, combinado honesto 0.51)
    y 'top10' (selección descarada de mejores células — su backtest no
    es creíble por construcción; la sombra existe para juzgarla con
    evidencia virgen). Un fallo aquí NUNCA afecta al trading del oro.
    """
    from gold_bot.risk.multi_asset import build_multi_portfolio, top_cells_exposures

    result = build_multi_portfolio()
    ts = datetime.now(UTC).isoformat()

    full = {}
    for key, book in result["books"].items():
        gate = float(result["book_gates"][key].iloc[-1])
        weight = float(result["asset_weights"][key].iloc[-1])
        lev = float(result["leverage"].iloc[-1])
        brake = float(result["brake"].iloc[-1])
        book_exp = float(book.net_exposure.dropna().iloc[-1]) if len(
            book.net_exposure.dropna()) else 0.0
        full[key] = book_exp * gate * weight * lev * brake
    top10 = top_cells_exposures(result["books"])

    # señal de CADA célula (activo × estrategia), incluido el libro del
    # oro completo: la validación individual de todas las estrategias
    # hacia delante — en 3 meses sabremos cuáles funcionan de verdad
    cells: list[tuple[str, str, float]] = []
    for asset, book in result["books"].items():
        for strat_name, positions in book.positions.items():
            pos = positions.dropna()
            last = float(pos.iloc[-1]) if len(pos) else 0.0
            cells.append((f"cell_{strat_name}", asset, last))

    conn = connect()
    try:
        for book_name, exposures in (("multi_full", full), ("top10", top10)):
            for asset, exposure in exposures.items():
                conn.execute(
                    "INSERT OR REPLACE INTO shadow_signals "
                    "(ts, book, asset, exposure) VALUES (?, ?, ?, ?)",
                    (ts, book_name, asset, exposure))
        for book_name, asset, exposure in cells:
            conn.execute(
                "INSERT OR REPLACE INTO shadow_signals "
                "(ts, book, asset, exposure) VALUES (?, ?, ?, ?)",
                (ts, book_name, asset, exposure))
        conn.commit()
    finally:
        conn.close()

    def fmt(d: dict) -> str:
        return "\n".join(f"<code>{k:4}</code> {v:+.1%}"
                         for k, v in sorted(d.items()) if abs(v) > 0.001) or "—"

    send_telegram(
        "<b>🌐 libros sombra (sin órdenes)</b>\n"
        "<b>multi completo:</b>\n" + fmt(full) +
        "\n\n<b>selección top10:</b>\n" + fmt(top10) +
        f"\n\n<i>{len(cells)} células estrategia×activo registradas "
        f"para validación individual</i>"
    )
    log.info("sombra_registrada", full=len(full), top10=len(top10),
             celulas=len(cells))


def main() -> None:
    """Entrada del cron: cualquier excepción se avisa por Telegram."""
    try:
        print(run(dry_run="--dry-run" in sys.argv))
    except Exception as exc:
        log.error("runner_fallo", error=str(exc))
        send_telegram(f"🚨 <b>gold-bot: el runner diario FALLÓ</b>\n<code>{exc}</code>")
        raise
    try:
        run_shadow_multi()
    except Exception as exc:  # la sombra jamás tumba al oro
        log.error("sombra_multi_fallo", error=str(exc))
        send_telegram(f"⚠️ libro sombra multi-activo falló: <code>{exc}</code>")


if __name__ == "__main__":
    main()
