"""Logging estructurado con structlog.

Uso en cualquier módulo:

    from gold_bot.utils.log import get_logger
    log = get_logger(__name__)
    log.info("descarga_completada", simbolo="XAUUSD", filas=125_000)

Los eventos son pares clave-valor, no strings sueltos: luego se pueden
filtrar y analizar (p. ej. todos los eventos de una estrategia concreta).
"""

import logging

import structlog

from gold_bot.config import settings

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    _configure()
    return structlog.get_logger(name)
