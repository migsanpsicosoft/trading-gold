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
  days: number
}
interface StrategyInfo {
  name: string
  description: string
  params: Record<string, number>
  type?: string
  oos_sharpe: number | null
  passes_filter: boolean
}
interface BacktestResponse {
  name: string
  description: string
  params: Record<string, number>
  metrics: { full: Metrics; is: Metrics; oos: Metrics; turnover_annual: number }
  oos_start: string
  equity: Point[]
  positions: Point[]
}

function EquityChart({ equity, oosStart }: { equity: Point[]; oosStart: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || equity.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d', mode: 1 }, // escala logarítmica
    })
    const oosEpoch = new Date(oosStart).getTime() / 1000

    const isSeries = chart.addSeries(LineSeries, {
      color: '#8b949e',
      lineWidth: 2,
      priceLineVisible: false,
    })
    isSeries.setData(
      equity.filter((p) => p.time < oosEpoch).map((p) => ({
        time: p.time as UTCTimestamp,
        value: p.value,
      })),
    )
    const oosSeries = chart.addSeries(LineSeries, {
      color: '#d4a017',
      lineWidth: 2,
      priceLineVisible: false,
    })
    oosSeries.setData(
      equity.filter((p) => p.time >= oosEpoch).map((p) => ({
        time: p.time as UTCTimestamp,
        value: p.value,
      })),
    )
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [equity, oosStart])

  return <div ref={ref} className="chart" />
}

function PositionsChart({ positions }: { positions: Point[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || positions.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d' },
    })
    const series = chart.addSeries(LineSeries, {
      color: '#58a6ff',
      lineWidth: 1,
      priceLineVisible: false,
      lineType: 1, // escalones: la posición cambia a saltos
    })
    series.setData(
      positions.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    )
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [positions])

  return <div ref={ref} className="chart chart-small" />
}

interface CorrData {
  names: string[]
  matrix: number[][]
}

/** rojo = correlación alta (solapan), verde = negativa (se cubren). */
function corrColor(v: number, isDiagonal: boolean): string {
  if (isDiagonal) return 'rgba(139, 148, 158, 0.15)'
  if (v >= 0) return `rgba(248, 81, 73, ${Math.min(v, 1) * 0.55})`
  return `rgba(63, 185, 80, ${Math.min(-v, 1) * 0.55})`
}

function CorrelationMatrix({ corr }: { corr: CorrData }) {
  return (
    <table className="table corr">
      <thead>
        <tr>
          <th></th>
          {corr.names.map((n) => (
            <th key={n}>{n}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {corr.names.map((row, i) => (
          <tr key={row}>
            <td>
              <strong>{row}</strong>
            </td>
            {corr.names.map((col, j) => (
              <td
                key={col}
                style={{ background: corrColor(corr.matrix[i][j], i === j), textAlign: 'center' }}
              >
                {corr.matrix[i][j].toFixed(2)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const fmt = (v: number | null | undefined, digits = 2, pct = false) =>
  v == null ? '—' : pct ? `${(v * 100).toFixed(digits)}%` : v.toFixed(digits)

function MetricsBlock({ title, m, highlight }: { title: string; m: Metrics; highlight?: boolean }) {
  return (
    <div className={`card metric ${highlight ? 'metric-highlight' : ''}`}>
      <span className="metric-label">{title}</span>
      <span className="metric-value">Sharpe {fmt(m.sharpe)}</span>
      <span className="muted small">
        CAGR {fmt(m.cagr, 1, true)} · DD {fmt(m.max_drawdown, 1, true)} · vol{' '}
        {fmt(m.vol, 1, true)}
      </span>
    </div>
  )
}

export default function Strategies() {
  const [catalog, setCatalog] = useState<StrategyInfo[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [backtest, setBacktest] = useState<BacktestResponse | null>(null)
  const [corr, setCorr] = useState<CorrData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/strategies')
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then((list: StrategyInfo[]) => {
        setCatalog(list)
        if (list.length > 0) setSelected(list[0].name)
      })
      .catch((e) => setError(String(e)))
    fetch('/api/strategies/correlation')
      .then((r) => r.json())
      .then(setCorr)
      .catch(() => {}) // la matriz es secundaria: no rompe la página
  }, [])

  useEffect(() => {
    if (!selected) return
    setBacktest(null)
    fetch(`/api/strategies/${selected}`)
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setBacktest)
      .catch((e) => setError(String(e)))
  }, [selected])

  if (error) {
    return (
      <div className="container">
        <div className="card error">{error}</div>
      </div>
    )
  }

  return (
    <div className="container wide">
      <header>
        <h1>Estrategias base</h1>
        <p className="muted">
          Backtest con costes reales (spread Dukascopy + slippage) y ejecución t+1 ·
          filtro de criba: Sharpe OOS &gt; 0.5
        </p>
      </header>

      <div className="toolbar">
        <div className="seg">
          {catalog.map((s) => (
            <button
              key={s.name}
              className={`seg-btn ${s.name === selected ? 'seg-active' : ''}`}
              onClick={() => setSelected(s.name)}
              title={s.description}
            >
              {s.passes_filter ? '✓ ' : ''}
              {s.name}
              {s.type === 'intradia' ? ' ⏱' : ''}
            </button>
          ))}
        </div>
        {backtest && (
          <span className="muted small">
            {backtest.description} · params {JSON.stringify(backtest.params)}
          </span>
        )}
      </div>

      {!backtest ? (
        <p className="muted">Ejecutando backtest…</p>
      ) : (
        <>
          <div className="metrics">
            <MetricsBlock title={`In-sample (hasta ${backtest.oos_start})`} m={backtest.metrics.is} />
            <MetricsBlock
              title={`Out-of-sample (desde ${backtest.oos_start})`}
              m={backtest.metrics.oos}
              highlight
            />
            <div className="card metric">
              <span className="metric-label">Veredicto criba (OOS &gt; 0.5)</span>
              <span className="metric-value">
                {backtest.metrics.oos.sharpe != null && backtest.metrics.oos.sharpe > 0.5
                  ? '✅ pasa'
                  : '❌ no pasa'}
              </span>
              <span className="muted small">
                turnover {fmt(backtest.metrics.turnover_annual, 1)}x/año
              </span>
            </div>
          </div>

          <h2>Equity curve (base 1.0, escala log) — gris: IS · dorado: OOS</h2>
          <div className="card chart-card">
            <EquityChart equity={backtest.equity} oosStart={backtest.oos_start} />
          </div>

          <h2>Posición efectiva (−1 corto · 0 fuera · +1 largo · intradía: media del día)</h2>
          <div className="card chart-card">
            <PositionsChart positions={backtest.positions} />
          </div>

          {corr && corr.names.length > 1 && (
            <>
              <h2>Correlación entre estrategias (retornos netos diarios)</h2>
              <p className="muted small">
                Verde/cero = diversifican (lo que buscamos) · rojo = solapan
              </p>
              <div className="card">
                <CorrelationMatrix corr={corr} />
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
