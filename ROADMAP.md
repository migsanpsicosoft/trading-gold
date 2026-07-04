# ROADMAP — gold-hybrid-bot

Progreso vivo del proyecto. El dashboard (Home) parsea este fichero:
mantener el formato `## Fase N — Título` + checkboxes `- [ ]` / `- [x]`.

## Fase 0 — Setup
- [x] Estructura del repo (paquete instalable `gold_bot`)
- [x] `pyproject.toml` con dependencias de Fase 0
- [x] Configuración con pydantic-settings + `.env.example`
- [x] Logging estructurado (structlog)
- [x] Backend del dashboard: API FastAPI (`/api/status`)
- [x] Frontend del dashboard: React + Vite + TypeScript (Home con estado del proyecto)
- [x] Repo privado en GitHub (migsanpsicosoft/trading-gold)
- [ ] Entorno levantado y validado en la máquina de Miguel

## Fase 1 — Datos
- [x] Fuente de datos diarios: yfinance (GC=F, SI=F, DX-Y.NYB, ^TNX, TIP)
- [x] Pipeline incremental (SQLite, solape 7d, hash por dataset)
- [x] Auto-actualización: al arrancar el backend si los datos tienen >24h + botón manual
- [x] Página "Data explorer" (velas TradingView + volumen + estado de datasets)
- [x] Intradía 15m XAU: Dukascopy bid/ask (spread real por barra), backfill por trozos
- [x] Features técnicas base (17, sin leakage, con tests; página "Features")
- [ ] Validado por Miguel

## Fase 2 — Estrategias base
- [ ] Definir la 8ª estrategia (solo hay 7 listadas)
- [ ] Framework común de estrategia (interfaz señal → posición)
- [ ] Trend following
- [ ] Breakout
- [ ] Mean reversion
- [ ] Stat arb XAU/XAG
- [ ] Macro (DXY, tipos reales)
- [ ] Volatility breakout
- [ ] VWAP intradía
- [ ] Estrategia nº 8
- [ ] Filtro: descartar Sharpe OOS < 0.5
- [ ] Página por estrategia en el dashboard

## Fase 3 — Detector de régimen (HMM)
- [ ] Features de régimen
- [ ] HMM entrenado + selección de nº de estados
- [ ] Vista de regímenes coloreados sobre el precio

## Fase 4 — Meta-modelo (XGBoost)
- [ ] Triple barrier labeling (implementación propia, testeada)
- [ ] Purged K-fold con embargo (implementación propia, testeada)
- [ ] Dataset de señales históricas
- [ ] XGBoost + SHAP
- [ ] Vista de decisiones del meta-modelo

## Fase 5 — Gestor de riesgo
- [ ] Sizing por volatilidad (ATR)
- [ ] Risk parity entre estrategias
- [ ] Límites duros (DD máximo, exposición máxima)
- [ ] Vista de exposición y stress tests

## Fase 6 — Ensemble completo
- [ ] Backtest walk-forward integrado con costes realistas
- [ ] Artefacto HTML por backtest
- [ ] Objetivo: Sharpe 1.2–1.8, DD < 15%

## Fase 7 — Paper trading
- [ ] Broker demo (MT5 u OANDA)
- [ ] Mínimo 3 meses de paper trading

## Fase 8 — Dinero real pequeño
- [ ] Solo si live ≈ backtest
