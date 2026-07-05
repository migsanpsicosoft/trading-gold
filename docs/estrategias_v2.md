# Pre-registro: estrategias personalizadas por activo (v2)

**Fecha: 2026-07-05 — escrito ANTES de ejecutar ningún backtest v2.**

Disciplina: los diseños salen de efectos documentados en la literatura,
no de nuestra tabla OOS v1 (que ya vimos y no podemos des-ver — la
contaminación queda declarada). Una sola iteración de diseño; los
resultados se aceptan como salgan y se suman al contador de intentos
del deflated Sharpe.

## Hipótesis y fuentes

1. **TSMomentum (12-1, rebalanceo mensual)** — universal no-oro.
   Moskowitz, Ooi & Pedersen (2012), 58 instrumentos: el retorno de los
   últimos 12 meses (saltando el último) predice el del mes siguiente
   en índices, divisas, commodities y bonos. Nuestro trend 50/200 diario
   opera OTRO horizonte; esta es la especificación canónica.

2. **ShortTermReversal (z de 5 días, continuo)** — universal no-oro.
   Reversión semanal documentada cross-asset; posición continua
   -clip(z/2) para turnover suave.

3. **MonthlySeasonality (adaptativa)** — universal no-oro.
   Estacionalidad mensual documentada en commodities (gas natural:
   ciclo de inyección/extracción). Como en session_seasonality: la
   deriva del mes se estima con años ANTERIORES y solo se opera con
   |t| > 1.5 — nada de cablear "compra agosto".

4. **OvernightEquity** — solo SPX (intradía).
   El retorno de índices se concentra cierre→apertura (Lou/Polk/Skouras;
   verificado vigente 2024-25). EXCEPCIÓN deliberada al contrato
   plana-overnight: la hipótesis ES el salto nocturno. Riesgo conocido:
   costes (2 cruces/día ≈ 2 pb) — la criba de costes decidirá.

5. **RiskOffJPY** — solo JPY.
   El yen es divisa refugio (Ranaldo & Söderlind): risk-off → JPY se
   fortalece. Posición USDJPY = signo del momentum 60d del S&P.

6. **MeanReversion (Bollinger)** se mantiene en todos los libros
   (hipótesis original de la Fase 2, universal).

## Decisiones a priori sobre los libros no-oro

- FUERA trend 50/200 y breakout 55/20: TSMOM los sustituye en su
  horizonte documentado.
- FUERA vol_breakout: sus costes medidos (spread relativo) ya lo
  mataron en todos los activos nuevos — decisión por costes, no por
  cherry-picking de resultados.
- El libro del ORO no se toca: está validado y en producción.

## Criterio de éxito (pre-declarado)

Se despliega el multi-activo v2 solo si el combinado (gate por libro +
parity + vol target 10% + freno B) iguala o supera al oro solo
(Sharpe OOS ≥ 0.70) sin empeorar el drawdown. Si no, se reporta y el
servidor sigue operando solo oro.
