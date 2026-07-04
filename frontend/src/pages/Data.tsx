import { useEffect, useRef, useState } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createChart,
  type UTCTimestamp,
} from 'lightweight-charts'

// --- Tipos que devuelve el backend ---
interface Bar {
  time: number // segundos epoch UTC
  open: number
  high: number
  low: number
  close: number
  volume: number | null
  spread?: number | null // solo intradía: ask - bid real de la barra
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

type Timeframe = 'D' | '1h' | '15m'

const TIMEFRAMES: { key: Timeframe; label: string }[] = [
  { key: 'D', label: 'Diario' },
  { key: '1h', label: '1h' },
  { key: '15m', label: '15m' },
]

// Rangos disponibles (en días) según timeframe
const RANGES: Record<'daily' | 'intraday', { label: string; days: number | null }[]> = {
  daily: [
    { label: '1A', days: 365 },
    { label: '3A', days: 3 * 365 },
    { label: '10A', days: 10 * 365 },
    { label: 'Todo', days: null },
  ],
  intraday: [
    { label: '1S', days: 7 },
    { label: '1M', days: 30 },
    { label: '3M', days: 90 },
    { label: '1A', days: 365 },
  ],
}

// Solo estos símbolos tienen datos intradía
const INTRADAY_SYMBOLS = ['XAU']

/** Gráfico de velas + volumen con lightweight-charts (TradingView). */
function CandleChart({ bars, showTime }: { bars: Bar[]; showTime: boolean }) {
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
      timeScale: { borderColor: '#30363d', timeVisible: showTime },
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
        time: b.time as UTCTimestamp,
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
          time: b.time as UTCTimestamp,
          value: b.volume ?? 0,
          color: b.close >= b.open ? 'rgba(63,185,80,0.4)' : 'rgba(248,81,73,0.4)',
        })),
      )
    }

    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [bars, showTime])

  return <div ref={ref} className="chart" />
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'nunca'
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 60) return `hace ${minutes} min`
  if (minutes < 60 * 24) return `hace ${Math.round(minutes / 60)} h`
  return `hace ${Math.round(minutes / (60 * 24))} días`
}

export default function Data() {
  const [summary, setSummary] = useState<SymbolSummary[]>([])
  const [symbol, setSymbol] = useState('XAU')
  const [timeframe, setTimeframe] = useState<Timeframe>('D')
  const [rangeDays, setRangeDays] = useState<number | null>(3 * 365)
  const [bars, setBars] = useState<Bar[]>([])
  const [updating, setUpdating] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const isIntraday = timeframe !== 'D'
  const ranges = RANGES[isIntraday ? 'intraday' : 'daily']

  const loadSummary = () =>
    fetch('/api/data/summary')
      .then((r) => r.json())
      .then(setSummary)
      .catch((e) => setError(String(e)))

  useEffect(() => {
    loadSummary()
  }, [])

  useEffect(() => {
    let url = `/api/data/bars/${symbol}?timeframe=${timeframe}`
    if (rangeDays != null) {
      const from = new Date(Date.now() - rangeDays * 86400_000)
      url += `&start=${from.toISOString().slice(0, 10)}`
    }
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setBars)
      .catch((e) => setError(String(e)))
  }, [symbol, timeframe, rangeDays, refresh])

  const selectTimeframe = (tf: Timeframe) => {
    setTimeframe(tf)
    if (tf === 'D') {
      setRangeDays(3 * 365)
    } else {
      setRangeDays(30)
      if (!INTRADAY_SYMBOLS.includes(symbol)) setSymbol('XAU')
    }
  }

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

  // Solo los símbolos diarios van al selector (el intradía es una fila aparte)
  const dailySymbols = summary.filter((s) => !s.symbol.includes('·'))
  const selected = dailySymbols.find((s) => s.symbol === symbol)

  const spreads = bars.map((b) => b.spread).filter((s): s is number => s != null)
  const avgSpread = spreads.length
    ? spreads.reduce((a, b) => a + b, 0) / spreads.length
    : null

  return (
    <div className="container wide">
      <header className="row-between">
        <div>
          <h1>Data explorer</h1>
          <p className="muted">
            Diario: Yahoo Finance · Intradía 15m: Dukascopy (bid/ask, spread real)
          </p>
        </div>
        <button className="btn" onClick={runUpdate} disabled={updating}>
          {updating ? 'Actualizando…' : '⟳ Actualizar datos'}
        </button>
      </header>

      {error && <div className="card error">{error}</div>}

      <div className="toolbar">
        <div className="seg">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.key}
              className={`seg-btn ${tf.key === timeframe ? 'seg-active' : ''}`}
              onClick={() => selectTimeframe(tf.key)}
            >
              {tf.label}
            </button>
          ))}
        </div>
        <div className="seg">
          {dailySymbols.map((s) => {
            const disabled = isIntraday && !INTRADAY_SYMBOLS.includes(s.symbol)
            return (
              <button
                key={s.symbol}
                className={`seg-btn ${s.symbol === symbol ? 'seg-active' : ''}`}
                onClick={() => setSymbol(s.symbol)}
                disabled={disabled}
                title={disabled ? 'Sin datos intradía' : s.description}
              >
                {s.symbol}
              </button>
            )
          })}
        </div>
        <div className="seg">
          {ranges.map((r) => (
            <button
              key={r.label}
              className={`seg-btn ${r.days === rangeDays ? 'seg-active' : ''}`}
              onClick={() => setRangeDays(r.days)}
            >
              {r.label}
            </button>
          ))}
        </div>
        {selected && (
          <span className="muted small">
            {selected.description} · {bars.length.toLocaleString()} barras
            {avgSpread != null && <> · spread medio {avgSpread.toFixed(3)} $</>}
          </span>
        )}
      </div>

      <div className="card chart-card">
        {bars.length > 0 ? (
          <CandleChart bars={bars} showTime={isIntraday} />
        ) : (
          <p className="muted">
            Sin datos para esta vista.
            {isIntraday && ' Si el intradía aún no se ha descargado, usa "Actualizar datos".'}
          </p>
        )}
      </div>

      <h2>Datasets</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Símbolo</th>
              <th>Fuente</th>
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
