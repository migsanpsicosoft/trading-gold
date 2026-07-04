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
    parity_oos: Metrics
    final_oos: Metrics
  }
  equity_raw: Point[]
  equity_gated: Point[]
  equity_final: Point[]
  gates_now: GateNow[]
  weights_now: Record<string, number>
  gate_on_pct: Record<string, number>
  current_leverage: number
  current_brake: number
  current_exposure: number
}

const REGIME_LABELS = ['calma', 'transición', 'turbulencia']

function EquityCompareChart({
  raw,
  gated,
  final,
}: {
  raw: Point[]
  gated: Point[]
  final: Point[]
}) {
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
    const mk = (data: Point[], color: string, width: 1 | 2) => {
      const s = chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        priceLineVisible: false,
        lastValueVisible: false,
      })
      s.setData(data.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })))
    }
    mk(raw, '#8b949e', 1)
    mk(gated, '#58a6ff', 1)
    mk(final, '#d4a017', 2)
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [raw, gated, final])

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

  const { raw_oos, gated_oos, parity_oos, final_oos } = data.metrics
  const currentRegime = data.gates_now[0]?.regime

  const layer = (label: string, m: Metrics, highlight = false) => (
    <div className={`card metric ${highlight ? 'metric-highlight' : ''}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">Sharpe {fmt(m.sharpe)}</span>
      <span className="muted small">
        CAGR {fmt(m.cagr, 1, true)} · DD {fmt(m.max_drawdown, 1, true)} · vol{' '}
        {fmt(m.vol, 1, true)}
      </span>
    </div>
  )

  return (
    <div className="container wide">
      <header>
        <h1>Riesgo — cartera por capas</h1>
        <p className="muted">
          gating por régimen → risk parity (1/vol 60d) → vol targeting 10% (tope
          2×) → freno de drawdown −6%/−12% (pico móvil 1 año) · config B
          aprobada
        </p>
      </header>

      <div className="metrics">
        {layer('1. Ensemble crudo 1/N (OOS)', raw_oos)}
        {layer('2. + gating por régimen (OOS)', gated_oos)}
        {layer('3. + risk parity (OOS)', parity_oos)}
        {layer('4. + vol target y freno (OOS)', final_oos, true)}
      </div>

      <div className="metrics">
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
        <div className="card metric">
          <span className="metric-label">Apalancamiento hoy</span>
          <span className="metric-value">{data.current_leverage}×</span>
          <span className="muted small">freno: ×{data.current_brake}</span>
        </div>
        <div className="card metric">
          <span className="metric-label">Exposición neta XAU hoy</span>
          <span className="metric-value">{data.current_exposure}</span>
          <span className="muted small">
            positivo largo · negativo corto · 0 en cash
          </span>
        </div>
      </div>

      <h2>
        Equity — gris: crudo · azul: gating 1/N · dorado: cartera completa
      </h2>
      <div className="card chart-card">
        <EquityCompareChart
          raw={data.equity_raw}
          gated={data.equity_gated}
          final={data.equity_final}
        />
      </div>

      <h2>Gates y pesos ahora mismo (régimen: {REGIME_LABELS[currentRegime] ?? '—'})</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Estrategia</th>
              <th>Sharpe en este régimen (250d)</th>
              <th>Gate</th>
              <th>Peso risk parity</th>
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
                  {data.weights_now[g.strategy] != null
                    ? `${(data.weights_now[g.strategy] * 100).toFixed(1)}%`
                    : '—'}
                </td>
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
