"""Endpoints de validación del ensemble (Fase 6): DSR, stress, informe."""

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from gold_bot.api.data import _data_version
from gold_bot.api.risk import _portfolio_for_version
from gold_bot.backtest.deflated_sharpe import deflated_sharpe
from gold_bot.backtest.report import REPORTS_DIR, build_report
from gold_bot.backtest.simple import OOS_START
from gold_bot.data.db import connect
from gold_bot.risk import portfolio as pf
from gold_bot.risk.stress import crisis_performance, drawdown_episodes, shock_table

router = APIRouter(prefix="/api/ensemble")


def _version() -> tuple:
    conn = connect()
    try:
        return _data_version(conn)
    finally:
        conn.close()


@lru_cache(maxsize=1)
def _validation_for_version(version: tuple) -> dict:
    _inputs, _comparison, portfolio = _portfolio_for_version(version)
    final = portfolio["final_returns"]
    oos = final[final.index >= OOS_START]
    exposure = float(portfolio["net_exposure"].dropna().iloc[-1])
    return {
        "dsr": deflated_sharpe(oos),
        "stress": {
            "episodes": drawdown_episodes(oos),
            "crisis": crisis_performance(final),
            "shocks": shock_table(exposure),
            "current_exposure": round(exposure, 3),
        },
    }


@router.get("")
def validation() -> dict:
    """DSR + stress tests de la cartera final (OOS)."""
    return _validation_for_version(_version())


@router.post("/report")
def generate_report() -> dict:
    """Genera el artefacto HTML reproducible del backtest actual."""
    version = _version()
    _inputs, comparison, portfolio = _portfolio_for_version(version)
    validation_data = _validation_for_version(version)

    layers = {
        "1. Ensemble crudo 1/N": comparison["metrics"]["raw_oos"],
        "2. + gating por régimen": comparison["metrics"]["gated_oos"],
        "3. + risk parity": portfolio["metrics"]["parity_oos"],
        "4. + vol targeting y freno (final)": portfolio["metrics"]["final_oos"],
    }
    params = {
        "TARGET_VOL": pf.TARGET_VOL,
        "MAX_LEVERAGE": pf.MAX_LEVERAGE,
        "BRAKE_SOFT / BRAKE_HARD": f"{pf.BRAKE_SOFT} / {pf.BRAKE_HARD}",
        "STRAT_VOL_LOOKBACK": pf.STRAT_VOL_LOOKBACK,
        "PORT_VOL_LOOKBACK": pf.PORT_VOL_LOOKBACK,
        "OOS_START": OOS_START,
    }
    path = build_report(
        final_returns=portfolio["final_returns"],
        layers=layers,
        dsr=validation_data["dsr"],
        stress=validation_data["stress"],
        data_hashes=[{"symbol": s, "hash": h} for s, h in version],
        params=params,
    )
    return {"file": path.name}


@router.get("/report/latest")
def latest_report() -> FileResponse:
    """Sirve el informe HTML más reciente."""
    reports = sorted(REPORTS_DIR.glob("backtest_*.html")) if REPORTS_DIR.exists() else []
    if not reports:
        raise HTTPException(status_code=404, detail="Aún no hay informes generados")
    return FileResponse(reports[-1], media_type="text/html")
