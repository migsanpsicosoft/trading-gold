"""Backend del dashboard: API JSON que consume el frontend React.

Arrancar en desarrollo:
    uvicorn gold_bot.api.main:app --reload --port 8100

El frontend (Vite, puerto 5173) proxya las llamadas /api/* hacia aquí,
así que en desarrollo no hay problemas de CORS entre ambos.

Puerto 8100 (no 8000) porque el backend de comerc-IA-l ya usa el 8000.
"""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException

from gold_bot import __version__
from gold_bot.config import PROJECT_ROOT, settings
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

app = FastAPI(title="Gold Hybrid Bot API", version=__version__)

# Módulos que el sistema tendrá cuando esté completo; el endpoint de
# estado comprueba cuáles existen ya en el filesystem (nada inventado).
EXPECTED_MODULES = {
    "config": "Configuración (pydantic-settings)",
    "utils": "Utilidades (logging estructurado)",
    "api": "Backend del dashboard (FastAPI)",
    "data": "Descarga, limpieza y features",
    "strategies": "Las 8 estrategias base",
    "regime": "Detector de régimen (HMM)",
    "meta_model": "Meta-labeling (XGBoost)",
    "risk": "Sizing y risk parity",
    "backtest": "Walk-forward con costes",
    "execution": "Broker interface",
}


def parse_roadmap(path: Path) -> list[dict]:
    """Extrae fases y checkboxes de ROADMAP.md."""
    phases: list[dict] = []
    current: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        header = re.match(r"^## (.+)$", line)
        if header:
            current = {"title": header.group(1).strip(), "items": []}
            phases.append(current)
            continue
        item = re.match(r"^- \[( |x)\] (.+)$", line)
        if item and current is not None:
            current["items"].append({"done": item.group(1) == "x", "text": item.group(2)})
    return phases


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/status")
def status() -> dict:
    """Estado real del proyecto: fases del ROADMAP + módulos existentes."""
    roadmap_path = PROJECT_ROOT / "ROADMAP.md"
    if not roadmap_path.exists():
        raise HTTPException(status_code=500, detail="ROADMAP.md no encontrado")

    phases = parse_roadmap(roadmap_path)
    current_phase = next(
        (p["title"] for p in phases if any(not i["done"] for i in p["items"])),
        phases[-1]["title"] if phases else None,
    )

    pkg_root = PROJECT_ROOT / "src" / "gold_bot"
    modules = [
        {
            "name": name,
            "description": desc,
            "exists": (pkg_root / name).is_dir() or (pkg_root / f"{name}.py").is_file(),
        }
        for name, desc in EXPECTED_MODULES.items()
    ]

    data_dirs = [
        {
            "name": label,
            "files": len([f for f in d.glob("*") if f.name != ".gitkeep"]) if d.exists() else 0,
        }
        for label, d in [
            ("raw", settings.raw_dir),
            ("processed", settings.processed_dir),
            ("models", settings.models_dir),
        ]
    ]

    return {
        "version": __version__,
        "current_phase": current_phase,
        "phases": phases,
        "modules": modules,
        "data_dirs": data_dirs,
        "random_seed": settings.random_seed,
    }
