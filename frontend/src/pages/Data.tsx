import { useEffect, useRef, useState } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createChart,
  type UTCTimestamp,
} from 'lightweight-charts'

// --- Tipos que devuelve el backend ---
interface Bar {
  time: string // 'yyyy-mm-dd'
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}
interface SymbolSummary {
  symbol: string
  yahoo_ticker: string
  description: string
  rows: number
  first_date: string | null
  last_date: string | null
  last_updated: string | null
  content_hash: string | null
}

/** Gráfico de velas + volumen con lightweight-charts (TradingView). */
function CandleChart({ bars }: { bars: Bar[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || bars.length === 0) return

    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d' },
    })

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: '#3fb950',
      downColor: '#f85149',
      borderVisible: false,
      wickUpColor: '#3fb950',
      wickDownColor: '#f85149',
    })
    candles.setData(
      bars.map((b) => ({
        time: (new Date(b.time).getTime() / 1000) as UTCTimestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    )

    const hasVolume = bars.some((b) => b.volume != null && b.volume > 0)
    if (hasVolume) {
      const volume = chart.addSeries(HistogramSeries, {
        priceScaleId: 'volume',
        priceFormat: { type: 'volume' },
        color: '#30363d',
      })
      chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      volume.setData(
        bars.map((b) => ({
          time: (new Date(b.time).getTime() / 1000) as UTCTimestamp,
          value: b.volume ?? 0,
          color: b.close >= b.open ? 'rgba(63,185,80,0.4)' : 'rgba(248,81,73,0.4)',
        })),
      )
    }

    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [bars])

  return <div ref={ref} className="chart" />
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'nunca'
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 60) return `hace ${minutes} min`
  if (minutes < 60 * 24) return `hace ${Math.round(minutes / 60)} h`
  return `hace ${Math.round(minutes / (60 * 24))} días`
}

const RANGES: { label: string; years: number | null }[] = [
  { label: '1A', years: 1 },
  { label: '3A', years: 3 },
  { label: '10A', years: 10 },
  { label: 'Todo', years: null },
]

export default function Data() {
  const [summary, setSummary] = useState<SymbolSummary[]>([])
  const [symbol, setSymbol] = useState('XAU')
  const [rangeYears, setRangeYears] = useState<number | null>(3)
  const [bars, setBars] = useState<Bar[]>([])
  const [updating, setUpdating] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const loadSummary = () =>
    fetch('/api/data/summary')
      .then((r) => r.json())
      .then(setSummary)
      .catch((e) => setError(String(e)))

  useEffect(() => {
    loadSummary()
  }, [])

  useEffect(() => {
    let url = `/api/data/bars/${symbol}`
    if (rangeYears != null) {
      const from = new Date()
      from.setFullYear(from.getFullYear() - rangeYears)
      url += `?start=${from.toISOString().slice(0, 10)}`
    }
    fetch(url)
      .then((r) => r.json())
      .then(setBars)
      .catch((e) => setError(String(e)))
  }, [symbol, rangeYears, refresh])

  const runUpdate = async () => {
    setUpdating(true)
    setError(null)
    try {
      const r = await fetch('/api/data/update', { method: 'POST' })
      if (!r.ok) throw new Error(`API respondió ${r.status}`)
      await loadSummary()
      setRefresh((n) => n + 1) // re-dispara la carga de velas
    } catch (e) {
      setError(String(e))
    } finally {
      setUpdating(false)
    }
  }

  const selected = summary.find((s) => s.symbol === symbol)

  return (
    <div className="container wide">
      <header className="row-between">
        <div>
          <h1>Data explorer</h1>
          <p className="muted">
            OHLCV diario desde Yahoo Finance — incremental, con hash por dataset
          </p>
        </div>
        <button className="btn" onClick={runUpdate} disabled={updating}>
          {updating ? 'Actualizando…' : '⟳ Actualizar datos'}
        </button>
      </header>

      {error && <div className="card error">{error}</div>}

      <div className="toolbar">
        <div className="seg">
          {summary.map((s) => (
            <button
              key={s.symbol}
              className={`seg-btn ${s.symbol === symbol ? 'seg-active' : ''}`}
              onClick={() => setSymbol(s.symbol)}
              title={s.description}
            >
              {s.symbol}
            </button>
          ))}
        </div>
        <div className="seg">
          {RANGES.map((r) => (
            <button
              key={r.label}
              className={`seg-btn ${r.years === rangeYears ? 'seg-active' : ''}`}
              onClick={() => setRangeYears(r.years)}
            >
              {r.label}
            </button>
          ))}
        </div>
        {selected && (
          <span className="muted small">
            {selected.description} · {bars.length} barras
          </span>
        )}
      </div>

      <div className="card chart-card">
        {bars.length > 0 ? <CandleChart bars={bars} /> : <p className="muted">Sin datos aún.</p>}
      </div>

      <h2>Datasets</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Símbolo</th>
              <th>Ticker Yahoo</th>
              <th>Filas</th>
              <th>Rango</th>
              <th>Actualizado</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            {summary.map((s) => (
              <tr key={s.symbol}>
                <td>
                  <strong>{s.symbol}</strong>{' '}
                  <span className="muted small">{s.description}</span>
                </td>
                <td>
                  <code>{s.yahoo_ticker}</code>
                </td>
                <td>{s.rows.toLocaleString()}</td>
                <td className="muted">
                  {s.first_date} → {s.last_date}
                </td>
                <td>{relativeTime(s.last_updated)}</td>
                <td>
                  <code className="muted">{s.content_hash?.slice(0, 12) ?? '—'}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
