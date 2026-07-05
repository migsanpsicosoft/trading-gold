# Pre-registro: estrategias v3 con datos nuevos (COT, carry, VIX)

**Fecha: 2026-07-05 — escrito ANTES de ejecutar ningún backtest v3.**

La conclusión de v1/v2 fue que sin información nueva no hay edge que
rescatar fuera del oro. v3 añade tres fuentes que los precios no
contienen y sus estrategias documentadas.

## Datos nuevos

- **COT (CFTC)**: posicionamiento semanal no-comercial desde 2005,
  los 9 activos. Anti-lookahead: informe del martes disponible desde
  el lunes siguiente (lag de 6 días aplicado en la carga).
- **Tipos cortos (FRED, sin key)**: DTB3 (US), ECBDFR (BCE),
  IRSTCI01JPM156N (Japón) — carry FX. T10Y2Y — pendiente de curva USA.
- **VIX y VIX3M** (yahoo): estructura temporal de volatilidad.

## Hipótesis (una por estrategia, con su literatura)

1. **cot_extreme** — todos los libros no-oro. Extremos de
   posicionamiento especulativo anticipan reversión (el último
   comprador ya compró; documentado en FX y commodities). Contrarian:
   corto si z(net_spec, 3 años) > +2, largo si < −2, salida en |z|<0.5.
2. **fx_carry** — EUR y JPY. El carry es EL factor documentado de FX
   (Lustig-Verdelhan y decenas más): largo la divisa de tipo alto.
   EURUSD: signo(BCE − US3M); USDJPY: signo(US3M − Japón). Banda
   muerta de 0.25 pp (sin señal si los tipos están empatados).
3. **curve_carry** — USB. Pendiente 10a-2a positiva = carry+rolldown
   positivo de estar largo duración (documentado en renta fija);
   inversión de curva → corto. Banda muerta ±0.10 pp.
4. **vix_structure** — SPX. Contango del VIX (VIX3M > VIX) = prima de
   riesgo cobrable, largo equity; backwardation = estrés, corto.
   Banda muerta ±2% del ratio.

## Libros v3

v2 (TSMOM, reversión 5d, Bollinger, estacionalidad mensual y
especiales) + las 4 nuevas donde correspondan. El oro sigue congelado.

## Criterio de éxito (idéntico, pre-declarado)

Combinado (gate por libro + parity + vol target 10% + freno B) con
Sharpe OOS ≥ 0.70 y DD no peor que el oro solo. Si no llega: se
reporta, no se despliega, y se discute antes de cualquier iteración.
