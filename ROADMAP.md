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
- [x] Validado por Miguel (2026-07-04)

## Fase 2 — Estrategias base
- [x] 8ª estrategia definida e implementada: seasonality de sesiones (adaptativa, t-stat móvil 90d — OOS bruto 0.04: sin edge claro, DD -9%)
- [x] Framework común (posición objetivo [-1,1], ejecución t+1, registro STRATEGIES)
- [x] Motor de criba: backtest vectorizado con spread real + slippage, split IS/OOS
- [x] Página "Estrategias" (equity IS/OOS, posiciones, veredicto del filtro)
- [x] Trend following (SMA 50/200 — OOS Sharpe 0.40, pendiente de mejora vía régimen/meta)
- [x] Breakout (Donchian 55/20 — OOS Sharpe 0.28; corr 0.80 con TF, vigilar redundancia)
- [x] Mean reversion (Bollinger z 20d — OOS Sharpe -0.04; corr -0.6/-0.7 con las trend: diversifica)
- [x] Matriz de correlación entre estrategias en el dashboard
- [x] Stat arb XAU/XAG (z-score ratio 60d — OOS Sharpe -0.15; corr bajas: diversifica)
- [x] Macro DXY + tipos reales (votos ±0.5 — OOS Sharpe 0.19)
- [x] Volatility breakout intradía (opening range 15m — OOS bruto 0.47, neto -0.14: edge comido por costes; corr ~0 con todo)
- [x] VWAP reversion intradía (OOS bruto -0.85, neto -1.54: sin edge — candidata firme a descarte en la criba)
- [x] Página de estrategias en el dashboard (selector, equity IS/OOS, posiciones, matriz 8×8)
- [x] Criba final aprobada por Miguel: fuera vwap_reversion (sin edge bruto); 7 vivas, stat_arb y session_seasonality en observación hasta post-meta-modelo

## Fase 3 — Detector de régimen (HMM)
- [x] Features de régimen (ret_1d + log vol_20d, estandarizadas solo con el train)
- [x] HMM gaussiano 3 estados, walk-forward (re-fit anual), probabilidades FILTRADAS (forward propio)
- [x] Estados ordenados por vol (0 calma / 1 transición / 2 turbulencia), estables entre re-fits
- [x] Vista "Régimen": precio coloreado, probabilidades, y Sharpe por régimen de cada estrategia
- [x] Evidencia: trend Sharpe ~1.0 en calma y negativo en turbulencia; mean_rev y vol_breakout al revés (+1.2 en turbulencia)
- [ ] Validado por Miguel

## Fase 4 — Meta-modelo (XGBoost)
- [x] Triple barrier labeling (implementación propia, testeada)
- [x] Purged K-fold con embargo (implementación propia, testeada)
- [x] Dataset de señales históricas (3.468 eventos de las 7 estrategias)
- [x] XGBoost walk-forward + estudio ventana×reentreno (6 configs simuladas)
- [x] Vista "Meta-modelo" (AUC, uplift, importancia, decisiones)
- [x] Resultado honesto: AUC ~0.51-0.52 en labels v1 (barrier) y v2 (PnL propio) — sin skill accionable a nivel de señal individual
- [ ] Decidir con Miguel el uso del edge débil: sizing continuo vs gating adaptativo por régimen vs congelar meta
- [ ] SHAP (pendiente de que haya un modelo con skill que explicar)

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
