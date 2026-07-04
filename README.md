# gold-hybrid-bot

Sistema híbrido de trading algorítmico en oro (XAU/USD): 8 estrategias base
descorrelacionadas + detector de régimen (HMM) + meta-labeling (XGBoost) +
gestión de riesgo por volatilidad. Referencia: *Advances in Financial
Machine Learning*, M. López de Prado.

**Estado y progreso:** ver [ROADMAP.md](ROADMAP.md) o la página Home del dashboard.

## Arquitectura del dashboard

Dos procesos en desarrollo:

- **Backend** — FastAPI (Python, puerto 8100): expone los datos como API JSON.
- **Frontend** — React + Vite + TypeScript (puerto 5173): consume la API.
  Vite proxya `/api/*` → `localhost:8100`, así que no hay CORS en desarrollo.

(El puerto es 8100 y no 8000 porque el backend de comerc-IA-l usa el 8000.)

## Setup (Windows / PowerShell)

Primera vez:

```powershell
# Python
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"

# Frontend
cd frontend
npm install
cd ..
```

Levantar el dashboard (dos terminales):

```powershell
# Terminal 1 — backend
.venv\Scripts\Activate.ps1
uvicorn gold_bot.api.main:app --reload --port 8100

# Terminal 2 — frontend  →  abre http://localhost:5173
cd frontend
npm run dev
```

## Estructura

```
├── data/               # raw / processed / models (fuera de git)
├── src/gold_bot/       # paquete instalable: config, utils, api, y módulos por fase
├── frontend/           # dashboard React + Vite + TypeScript
├── notebooks/          # exploración e informes
├── tests/              # pytest
├── ROADMAP.md          # progreso vivo (lo parsea el dashboard vía /api/status)
└── pyproject.toml
```

## Comandos útiles

```powershell
pytest              # tests
ruff check .        # lint
ruff format .       # formateo (sustituye a black)
```
