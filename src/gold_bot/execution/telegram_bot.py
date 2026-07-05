"""Bot interactivo de Telegram: estado y peticiones bajo demanda.

Servicio persistente (systemd gold-bot-telegram) que atiende SOLO al
chat_id configurado en el .env (cualquier otro chat se ignora — el
token da control del bot, pero las órdenes solo las da Miguel).

Comandos:
  /status     estado de servicios, datos y última ejecución
  /posiciones posición y balance actuales en el broker
  /informe    informe completo bajo demanda (tarda 1-3 min)
  /actualizar fuerza la actualización incremental de datos
  /ayuda      esta lista

Si el .env no tiene token/chat_id, duerme y re-comprueba cada minuto —
así el servicio puede arrancar antes de configurar las credenciales.
"""

import time
from datetime import UTC, datetime

import requests

from gold_bot.utils.log import get_logger

log = get_logger(__name__)

POLL_TIMEOUT = 50
API = "https://api.telegram.org/bot{token}/{method}"


def _fresh_settings():
    """Relee el .env en cada ciclo (permite configurar sin reiniciar)."""
    from gold_bot.config import Settings

    return Settings()


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        requests.post(API.format(token=token, method="sendMessage"),
                      json={"chat_id": chat_id, "text": text,
                            "parse_mode": "HTML"}, timeout=20)
    except Exception as exc:
        log.error("bot_envio_fallo", error=str(exc))


def _cmd_status() -> str:
    from gold_bot.data.db import connect

    conn = connect()
    try:
        last_run = conn.execute(
            "SELECT ts, exposure, balance, currency, dry_run FROM live_log "
            "ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        last_data = conn.execute(
            "SELECT MAX(last_updated) FROM dataset_meta"
        ).fetchone()[0]
        n_bars = conn.execute("SELECT COUNT(*) FROM intraday_bars").fetchone()[0]
    finally:
        conn.close()

    try:
        r = requests.get("http://127.0.0.1:8100/api/health", timeout=5)
        dashboard = "🟢 OK" if r.ok else f"🔴 {r.status_code}"
    except Exception:
        dashboard = "🔴 no responde"

    runner = "— aún sin ejecuciones"
    if last_run:
        mode = " (dry)" if last_run[4] else ""
        runner = (f"{last_run[0][:16]}{mode} · exp {last_run[1]:+.1%} · "
                  f"{last_run[2]:,.0f} {last_run[3]}")
    return (
        "<b>🥇 gold-bot /status</b>\n"
        f"Dashboard: {dashboard}\n"
        f"Última ejecución: {runner}\n"
        f"Datos actualizados: {(last_data or '—')[:16]}\n"
        f"Barras intradía: {n_bars:,}\n"
        f"Hora servidor: {datetime.now(UTC).isoformat()[:16]} UTC"
    )


def _cmd_posiciones() -> str:
    from gold_bot.execution.paper_broker import PaperBroker, get_broker

    try:
        broker = get_broker()
        state = broker.state()
    except Exception as exc:
        return f"🔴 error consultando el broker: {exc}"
    modo = "paper interno" if isinstance(broker, PaperBroker) else "OANDA"
    return (
        f"<b>🥇 gold-bot posiciones ({modo})</b>\n"
        f"Balance: <b>{state.balance:,.2f} {state.currency}</b>\n"
        f"Posición XAU: <b>{state.held_units:+.0f} oz</b>\n"
        f"XAU mid: {state.mid:.2f}$ (spread {state.ask - state.bid:.2f})"
    )


def _cmd_actualizar() -> str:
    from gold_bot.data.db import connect
    from gold_bot.data.download import update_all
    from gold_bot.data.intraday import (
        INTRADAY_SYMBOLS,
        has_intraday_data,
        update_intraday,
    )

    conn = connect()
    try:
        results = update_all(conn)
        daily_rows = sum(r.get("rows_upserted", 0) for r in results)
        intra_rows = 0
        for symbol in INTRADAY_SYMBOLS:
            if has_intraday_data(conn, symbol):
                intra_rows += update_intraday(conn, symbol)["rows_upserted"]
    finally:
        conn.close()
    return (f"✅ datos actualizados: {daily_rows} filas diarias, "
            f"{intra_rows} intradía")


def _cmd_informe() -> str:
    """Informe completo bajo demanda (sin enviar órdenes)."""
    from gold_bot.execution.daily_run import run

    result = run(dry_run=True)  # el propio run envía el informe por Telegram
    return (f"(informe generado — señal del {result['signal_date']}, "
            f"exposición {result['exposure']:+.1%})")


COMMANDS = {
    "/status": _cmd_status,
    "/posiciones": _cmd_posiciones,
    "/actualizar": _cmd_actualizar,
    "/informe": _cmd_informe,
}

HELP = ("<b>Comandos</b>\n/status — servicios y datos\n"
        "/posiciones — broker\n/informe — informe completo (1-3 min)\n"
        "/actualizar — refresca datos\n/ayuda — esto")


def dispatch(text: str) -> str:
    """Resuelve un comando a su respuesta (puro salvo los handlers)."""
    cmd = text.strip().split()[0].lower() if text.strip() else ""
    handler = COMMANDS.get(cmd)
    if handler is None:
        return HELP
    return handler()


def main() -> None:
    offset = None
    log.info("bot_arrancado")
    while True:
        s = _fresh_settings()
        if not (s.telegram_bot_token and s.telegram_chat_id):
            time.sleep(60)
            continue
        try:
            r = requests.get(
                API.format(token=s.telegram_bot_token, method="getUpdates"),
                params={"timeout": POLL_TIMEOUT, "offset": offset},
                timeout=POLL_TIMEOUT + 10,
            )
            for update in r.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                if chat_id != str(s.telegram_chat_id):
                    log.warning("bot_chat_desconocido", chat=chat_id)
                    continue
                log.info("bot_comando", texto=text)
                if text.strip().lower().startswith(("/informe", "/actualizar")):
                    _send(s.telegram_bot_token, chat_id, "⏳ en ello, dame 1-3 min…")
                try:
                    _send(s.telegram_bot_token, chat_id, dispatch(text))
                except Exception as exc:
                    _send(s.telegram_bot_token, chat_id, f"🔴 error: {exc}")
        except Exception as exc:
            log.error("bot_poll_fallo", error=str(exc))
            time.sleep(15)


if __name__ == "__main__":
    main()
