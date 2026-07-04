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
interface GateNow {
  strategy: string
  regime: number
  cond_sharpe: number | null
  gate_on: boolean
}
interface RiskResponse {
  metrics: {
    raw_oos: Metrics
    gated_oos: Metrics
    raw_full: Metrics
    gated_full: Metrics
  }
  equity_raw: Point[]
  equity_gated: Point[]
  gates_now: GateNow[]
  gate_on_pct: Record<string, number>
}

const REGIME_LABELS = ['calma', 'transición', 'turbulencia']

function EquityCompareChart({ raw, gated }: { raw: Point[]; gated: Point[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || raw.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d', mode: 1 },
    })
    const rawSeries = chart.addSeries(LineSeries, {
      color: '#8b949e',
      lineWidth: 1,
      priceLineVisible: false,
    })
    rawSeries.setData(raw.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })))
    const gatedSeries = chart.addSeries(LineSeries, {
      color: '#d4a017',
      lineWidth: 2,
      priceLineVisible: false,
    })
    gatedSeries.setData(
      gated.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    )
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [raw, gated])

  return <div ref={ref} className="chart" />
}

const fmt = (v: number | null | undefined, d = 2, pct = false) =>
  v == null ? '—' : pct ? `${(v * 100).toFixed(1)}%` : v.toFixed(d)

export default function Risk() {
  const [data, setData] = useState<RiskResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/risk')
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
        Calculando ensemble y gates (la primera vez tarda ~1 min)…
      </div>
    )
  }

  const { raw_oos, gated_oos } = data.metrics
  const currentRegime = data.gates_now[0]?.regime

  return (
    <div className="container wide">
      <header>
        <h1>Riesgo — ensemble con gating por régimen</h1>
        <p className="muted">
          Cada estrategia se enciende/apaga según su Sharpe móvil en el régimen
          actual (250 días en-régimen, aprendido walk-forward) · 1/N; el sizing
          por volatilidad y risk parity llegan en los próximos pasos
        </p>
      </header>

      <div className="metrics">
        <div className="card metric">
          <span className="metric-label">Ensemble crudo (OOS)</span>
          <span className="metric-value">Sharpe {fmt(raw_oos.sharpe)}</span>
          <span className="muted small">
            CAGR {fmt(raw_oos.cagr, 1, true)} · DD {fmt(raw_oos.max_drawdown, 1, true)}
          </span>
        </div>
        <div className="card metric metric-highlight">
          <span className="metric-label">Ensemble con gating (OOS)</span>
          <span className="metric-value">Sharpe {fmt(gated_oos.sharpe)}</span>
          <span className="muted small">
            CAGR {fmt(gated_oos.cagr, 1, true)} · DD{' '}
            {fmt(gated_oos.max_drawdown, 1, true)}
          </span>
        </div>
        <div className="card metric">
          <span className="metric-label">Régimen actual</span>
          <span className="metric-value">
            {currentRegime != null ? REGIME_LABELS[currentRegime] : '—'}
          </span>
          <span className="muted small">
            {data.gates_now.filter((g) => g.gate_on).length} de{' '}
            {data.gates_now.length} estrategias activas
          </span>
        </div>
      </div>

      <h2>Equity del ensemble — gris: crudo 1/N · dorado: con gating</h2>
      <div className="card chart-card">
        <EquityCompareChart raw={data.equity_raw} gated={data.equity_gated} />
      </div>

      <h2>Gates ahora mismo (régimen: {REGIME_LABELS[currentRegime] ?? '—'})</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Estrategia</th>
              <th>Sharpe en este régimen (250d)</th>
              <th>Gate</th>
              <th>% tiempo ON (desde 2012)</th>
            </tr>
          </thead>
          <tbody>
            {data.gates_now.map((g) => (
              <tr key={g.strategy}>
                <td>
                  <code>{g.strategy}</code>
                </td>
                <td>{fmt(g.cond_sharpe)}</td>
                <td>{g.gate_on ? '🟢 activa' : '🔴 apagada'}</td>
                <td>
                  {data.gate_on_pct[g.strategy] != null
                    ? `${(data.gate_on_pct[g.strategy] * 100).toFixed(0)}%`
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
