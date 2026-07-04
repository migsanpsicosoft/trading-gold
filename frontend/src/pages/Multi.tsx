import { useEffect, useRef, useState } from 'react'
import { LineSeries, createChart, type UTCTimestamp } from 'lightweight-charts'

interface Point {
  time: number
  value: number
}
interface Metrics {
  sharpe: number | null
  cagr: number | null
  max_drawdown: number | null
  vol: number | null
}
interface AssetRow {
  key: string
  name: string
  oos: Metrics
  per_strategy: Record<string, number | null>
  has_intraday: boolean
  weight_now: number
}
interface MultiResponse {
  per_asset: AssetRow[]
  correlation: { names: string[]; matrix: number[][] }
  combined_oos: Metrics
  gold_only_oos: Metrics
  equity_combined: Point[]
  equity_gold_only: Point[]
  leverage_now: number
  brake_now: number
}

const fmt = (v: number | null | undefined, d = 2, pct = false) =>
  v == null ? '—' : pct ? `${(v * 100).toFixed(1)}%` : v.toFixed(d)

function corrColor(v: number, diag: boolean): string {
  if (diag) return 'rgba(139,148,158,0.15)'
  if (v >= 0) return `rgba(248,81,73,${Math.min(v, 1) * 0.55})`
  return `rgba(63,185,80,${Math.min(-v, 1) * 0.55})`
}

function CompareChart({ combined, goldOnly }: { combined: Point[]; goldOnly: Point[] }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current || combined.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d', mode: 1 },
    })
    const g = chart.addSeries(LineSeries, {
      color: '#8b949e',
      lineWidth: 1,
      priceLineVisible: false,
    })
    g.setData(goldOnly.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })))
    const c = chart.addSeries(LineSeries, {
      color: '#d4a017',
      lineWidth: 2,
      priceLineVisible: false,
    })
    c.setData(combined.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [combined, goldOnly])
  return <div ref={ref} className="chart" />
}

export default function Multi() {
  const [data, setData] = useState<MultiResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/multi')
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setData)
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
        Construyendo los libros de todos los activos (la primera vez tarda 2-4 min)…
      </div>
    )
  }

  const strategyNames = Array.from(
    new Set(data.per_asset.flatMap((a) => Object.keys(a.per_strategy))),
  )

  return (
    <div className="container wide">
      <header>
        <h1>Cartera multi-activo</h1>
        <p className="muted">
          Un libro por activo (estrategias universales + HMM propio + gating +
          parity) → parity entre activos → vol target 10% → freno · todo
          walk-forward con costes reales
        </p>
      </header>

      <div className="metrics">
        <div className="card metric">
          <span className="metric-label">Solo oro (OOS)</span>
          <span className="metric-value">Sharpe {fmt(data.gold_only_oos.sharpe)}</span>
          <span className="muted small">
            CAGR {fmt(data.gold_only_oos.cagr, 1, true)} · DD{' '}
            {fmt(data.gold_only_oos.max_drawdown, 1, true)}
          </span>
        </div>
        <div className="card metric metric-highlight">
          <span className="metric-label">Multi-activo (OOS)</span>
          <span className="metric-value">Sharpe {fmt(data.combined_oos.sharpe)}</span>
          <span className="muted small">
            CAGR {fmt(data.combined_oos.cagr, 1, true)} · DD{' '}
            {fmt(data.combined_oos.max_drawdown, 1, true)}
          </span>
        </div>
        <div className="card metric">
          <span className="metric-label">Hoy</span>
          <span className="metric-value">lev {data.leverage_now}×</span>
          <span className="muted small">freno ×{data.brake_now}</span>
        </div>
      </div>

      <h2>Equity — gris: solo oro · dorado: multi-activo</h2>
      <div className="card chart-card">
        <CompareChart
          combined={data.equity_combined}
          goldOnly={data.equity_gold_only}
        />
      </div>

      <h2>Libros por activo (OOS 2019-hoy)</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Activo</th>
              <th>Sharpe</th>
              <th>CAGR</th>
              <th>Max DD</th>
              <th>Peso hoy</th>
              {strategyNames.map((s) => (
                <th key={s} className="muted small">
                  {s.slice(0, 10)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.per_asset.map((a) => (
              <tr key={a.key}>
                <td>
                  <strong>{a.key}</strong>{' '}
                  <span className="muted small">
                    {a.name}
                    {a.has_intraday ? '' : ' (sin intradía aún)'}
                  </span>
                </td>
                <td>{fmt(a.oos.sharpe)}</td>
                <td>{fmt(a.oos.cagr, 1, true)}</td>
                <td>{fmt(a.oos.max_drawdown, 1, true)}</td>
                <td>{(a.weight_now * 100).toFixed(0)}%</td>
                {strategyNames.map((s) => (
                  <td key={s} className="muted small">
                    {a.per_strategy[s] != null ? a.per_strategy[s]!.toFixed(2) : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Correlación entre libros (retornos OOS)</h2>
      <p className="muted small">La razón de ser del multi-activo: cuanto más verde/blanco, más suma cada libro</p>
      <div className="card">
        <table className="table corr">
          <thead>
            <tr>
              <th></th>
              {data.correlation.names.map((n) => (
                <th key={n}>{n}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.correlation.names.map((row, i) => (
              <tr key={row}>
                <td>
                  <strong>{row}</strong>
                </td>
                {data.correlation.names.map((col, j) => (
                  <td
                    key={col}
                    style={{
                      background: corrColor(data.correlation.matrix[i][j], i === j),
                      textAlign: 'center',
                    }}
                  >
                    {data.correlation.matrix[i][j].toFixed(2)}
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
