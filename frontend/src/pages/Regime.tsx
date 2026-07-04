import { useEffect, useRef, useState } from 'react'
import {
  LineSeries,
  createChart,
  type LineData,
  type UTCTimestamp,
  type WhitespaceData,
} from 'lightweight-charts'

interface RegimePoint {
  time: number
  regime: number
  probs: number[]
}
interface StateInfo {
  id: number
  label: string
  ann_return: number | null
  ann_vol: number | null
  days_pct: number
}
interface RegimeResponse {
  states: StateInfo[]
  series: RegimePoint[]
  sharpe_by_regime: Record<string, (number | null)[]>
}
interface Bar {
  time: number
  close: number
}

const REGIME_COLORS = ['#3fb950', '#d4a017', '#f85149'] // calma / transición / turbulencia

/** Precio coloreado por régimen: una serie por régimen con huecos. */
function RegimePriceChart({ series, price }: { series: RegimePoint[]; price: Bar[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || series.length === 0 || price.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d', mode: 1 },
    })
    const regimeByTime = new Map(series.map((p) => [p.time, p.regime]))

    for (let k = 0; k < REGIME_COLORS.length; k++) {
      const data: (LineData | WhitespaceData)[] = price.map((b) => {
        const t = b.time as UTCTimestamp
        return regimeByTime.get(b.time) === k ? { time: t, value: b.close } : { time: t }
      })
      const s = chart.addSeries(LineSeries, {
        color: REGIME_COLORS[k],
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      s.setData(data)
    }
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [series, price])

  return <div ref={ref} className="chart" />
}

/** Probabilidades filtradas de cada régimen en el tiempo. */
function ProbsChart({ series }: { series: RegimePoint[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || series.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d' },
    })
    for (let k = 0; k < REGIME_COLORS.length; k++) {
      const s = chart.addSeries(LineSeries, {
        color: REGIME_COLORS[k],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      s.setData(
        series.map((p) => ({ time: p.time as UTCTimestamp, value: p.probs[k] })),
      )
    }
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [series])

  return <div ref={ref} className="chart chart-small" />
}

const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? '—' : `${(v * 100).toFixed(digits)}%`

function sharpeColor(v: number | null): string {
  if (v == null) return 'transparent'
  if (v >= 0) return `rgba(63, 185, 80, ${Math.min(v / 2, 1) * 0.5})`
  return `rgba(248, 81, 73, ${Math.min(-v / 2, 1) * 0.5})`
}

export default function Regime() {
  const [data, setData] = useState<RegimeResponse | null>(null)
  const [price, setPrice] = useState<Bar[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/regime')
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch((e) => setError(String(e)))
    fetch('/api/data/bars/XAU?timeframe=D&start=2010-01-01')
      .then((r) => r.json())
      .then(setPrice)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) {
    return (
      <div className="container">
        <div className="card error">{error}</div>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="container muted">
        Entrenando HMM walk-forward (la primera vez tarda unos segundos)…
      </div>
    )
  }

  const current = data.series[data.series.length - 1]

  return (
    <div className="container wide">
      <header>
        <h1>Régimen de mercado (HMM)</h1>
        <p className="muted">
          Walk-forward (re-fit cada enero, solo con el pasado) · probabilidades
          filtradas, no suavizadas · estados ordenados por volatilidad
        </p>
      </header>

      <div className="metrics">
        {data.states.map((s) => (
          <div
            key={s.id}
            className="card metric"
            style={current.regime === s.id ? { borderColor: REGIME_COLORS[s.id] } : {}}
          >
            <span className="metric-label" style={{ color: REGIME_COLORS[s.id] }}>
              {s.id} — {s.label} {current.regime === s.id ? '← hoy' : ''}
            </span>
            <span className="metric-value">
              ret {fmtPct(s.ann_return)} · vol {fmtPct(s.ann_vol)}
            </span>
            <span className="muted small">{fmtPct(s.days_pct)} de los días</span>
          </div>
        ))}
      </div>

      <h2>Precio del oro coloreado por régimen detectado</h2>
      <div className="card chart-card">
        <RegimePriceChart series={data.series} price={price} />
      </div>

      <h2>Probabilidades filtradas P(régimen | datos hasta hoy)</h2>
      <div className="card chart-card">
        <ProbsChart series={data.series} />
      </div>

      <h2>Sharpe de cada estrategia según el régimen del día</h2>
      <p className="muted small">
        Si el régimen informa, cada estrategia debería tener su hábitat — esta
        tabla es la materia prima del meta-modelo (Fase 4)
      </p>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Estrategia</th>
              {data.states.map((s) => (
                <th key={s.id} style={{ color: REGIME_COLORS[s.id] }}>
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.sharpe_by_regime).map(([name, sharpes]) => (
              <tr key={name}>
                <td>
                  <code>{name}</code>
                </td>
                {sharpes.map((v, k) => (
                  <td key={k} style={{ background: sharpeColor(v), textAlign: 'center' }}>
                    {v == null ? '—' : v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
