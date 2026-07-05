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
- [x] Entorno levantado y validado en la máquina de Miguel

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
- [x] Decisión de Miguel: gating adaptativo por régimen (implementado en Fase 5); el meta XGBoost queda congelado con su infraestructura lista
- [ ] SHAP (pendiente de que haya un modelo con skill que explicar)

## Fase 5 — Gestor de riesgo
- [x] Gating adaptativo por régimen (Sharpe móvil 250d en-régimen, walk-forward): ensemble OOS 0.26→0.62, DD -14.5%→-7.8%
- [x] Página "Riesgo" (equity crudo vs gated, gates actuales)
- [x] Risk parity entre estrategias (1/vol 60d, shift 1) — OOS 0.62→0.70
- [x] Vol targeting 10% anual (vol 20d, tope 2×) con netting de las diarias en una posición
- [x] Freno de drawdown -6%/-12% contra pico móvil 1 año (rehabilitable) — cartera final OOS Sharpe 0.80, CAGR 8.2%, DD -14.6%
- [x] Config B de riesgo aprobada por Miguel (vol 10% + freno -6/-12)
- [x] Vista de cartera por capas, apalancamiento, freno y exposición actual
- [x] Stress tests (episodios, crisis, shocks — implementados en Fase 6)
- [x] Validado por Miguel (2026-07-04)

## Fase 6 — Ensemble completo
- [x] Backtest walk-forward integrado con costes reales: es la cartera por capas (HMM, gates, pesos, leverage y freno — todo walk-forward de punta a punta)
- [x] Deflated Sharpe Ratio: 0.18 (contabilidad conservadora, 24 intentos) / 0.89 (estricta, 9 configs de cartera); PSR vs 0: 0.99
- [x] Stress tests: peores episodios, ventanas de crisis (COVID +6.3%, dd −2.3%), shock instantáneo
- [x] Artefacto HTML reproducible (métricas, DSR, stress, SVGs, hashes de datos, commit, seed) — botón en la página Riesgo
- [x] Resultado vs objetivo: Sharpe OOS 0.80 (objetivo 1.2–1.8: NO alcanzado aún), DD −14.6% (< 15%: cumplido). El DSR conservador exige más evidencia OOS → paper trading

## Fase 7 — Paper trading
- [x] Simulador de cuenta (dry-run del ejecutor): órdenes discretas en oz, balance EUR, EURUSD diario, costes por orden. 2025 con 5.000€: +11.3% (DD −7.5%, 162 órdenes, 43€ de costes)
- [x] Broker elegido: OANDA practice (unidades de 1 oz — demo con 50k€ recomendada; el efecto 5k€ está cuantificado por el simulador)
- [x] Conector OANDA v20 (estado de cuenta, posición, orden a mercado)
- [x] Runner diario (`python -m gold_bot.execution.daily_run [--dry-run]`): datos → exposición → orden por diferencia → live_log
- [x] Página "Live": tracking live vs backtest + registro de ejecuciones
- [x] Informe diario por Telegram + alertas de error del runner
- [x] Desplegado en EC2 (Ubuntu 24.04): systemd `gold-bot-dashboard` (127.0.0.1:8100, acceso por túnel SSH), cron lun-vie 23:05 UTC, swap 2G, DB transferida
- [x] Runner validado en servidor de punta a punta (falla limpio solo en credenciales)
- [x] Paper broker INTERNO (sin broker externo ni KYC): cuenta virtual 50k€, fills al spread real, mark-to-market — OANDA quedó descartado (no disponible en España) y el interno mide lo mismo con más control
- [x] PAPER TRADING INICIADO 2026-07-05: primera orden real ejecutada (corto 1 oz @ 4187, exposición −7.1% con freno activo); sombras multi_full y top10 registrando
- [x] Telegram operativo: token + chat_id configurados, bot interactivo respondiendo, informes nocturnos activados (2026-07-05)
- [ ] Mínimo 3 meses de paper trading (hasta ~2026-10-05)

## Expansión multi-activo (research 2026-07-05)
- [x] Universo de 9 activos: datos diarios (2005→) + intradía 15m bid/ask (2019→, oro 2015→) — ~1.7M barras, integridad verificada
- [x] Libro por activo (estrategias universales + HMM propio + gating + parity) y cartera global con gate por libro
- [x] Resultado honesto: libros nuevos sin edge suficiente (JPY 0.25, NG 0.23, resto ~0 o negativo); correlación entre libros ~0.00 (diversificación perfecta pero sin edge que diversificar). Combinado 0.24 < oro solo 0.70 → NO desplegado
- [x] Página "Multi-activo" con los números completos
- [x] v2: estrategias personalizadas por activo, pre-registradas en docs/estrategias_v2.md (TSMOM 12-1, reversión 5d, estacionalidad mensual adaptativa, overnight SPX, yen refugio)
- [x] Resultado v2 honesto: combinado 0.24→0.34, sigue < 0.70 del oro → NO desplegado para operar. Ganadores: monthly_seasonality (positiva en 7/8, USB 0.73, SPX 0.58) y TSMOM en financieros (JPY 0.40, SPX 0.34); muertos con honor: overnight_equity (−3.06, costes — el precedente NightShares se confirmó) y TSMOM en WTI (−0.75)
- [x] v3 con DATOS nuevos: COT (CFTC, lag de publicación correcto), carry FX/curva (FRED sin key), estructura VIX — pre-registro en docs/estrategias_v3.md
- [x] Resultado v3: celdas con edge real (cot_extreme SPX 0.71, fx_carry JPY 0.45, vix_structure 0.45) pero combinado 0.35; con la criba de Fase 2 aplicada por libro: 0.51 — sigue < 0.70 → NO sustituye al oro (contador DSR: 53 intentos)
- [x] Decisión: multi-activo desplegado como LIBRO SOMBRA en el paper (exposiciones registradas y en Telegram, SIN órdenes) — 3 meses de evidencia virgen decidirán
- [ ] Research pendiente: term structure de futuros (carry de commodities — sin fuente gratuita fiable)

## Fase 7bis — Operación y monitorización (2026-07-05)
- [x] Informe diario de Telegram con TODAS las señales por estrategia
- [x] Bot interactivo de Telegram: /status /posiciones /informe /actualizar (servicio systemd)
- [ ] Miguel: credenciales OANDA + Telegram al .env del servidor

## Fase 8 — Dinero real pequeño
- [ ] Solo si live ≈ backtest
