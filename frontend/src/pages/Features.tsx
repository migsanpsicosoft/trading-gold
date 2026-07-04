import { useEffect, useRef, useState } from 'react'
import { LineSeries, createChart, type UTCTimestamp } from 'lightweight-charts'

interface Point {
  time: number
  value: number
}
interface Bar {
  time: number
  close: number
}
interface FeaturesMeta {
  names: string[]
  descriptions: Record<string, string>
  latest_date: string
  latest: Record<string, number | null>
}

const RANGES: { label: string; days: number | null }[] = [
  { label: '1A', days: 365 },
  { label: '3A', days: 3 * 365 },
  { label: '10A', days: 10 * 365 },
  { label: 'Todo', days: null },
]

/** Feature (escala izquierda, azul) sobre el precio del oro (derecha, dorado). */
function FeatureChart({ feature, price }: { feature: Point[]; price: Bar[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || feature.length === 0) return

    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d' },
      leftPriceScale: { borderColor: '#30363d', visible: true },
    })

    const priceSeries = chart.addSeries(LineSeries, {
      color: 'rgba(212, 160, 23, 0.55)',
      lineWidth: 1,
      priceScaleId: 'right',
      priceLineVisible: false,
    })
    priceSeries.setData(
      price.map((b) => ({ time: b.time as UTCTimestamp, value: b.close })),
    )

    const featSeries = chart.addSeries(LineSeries, {
      color: '#58a6ff',
      lineWidth: 2,
      priceScaleId: 'left',
      priceLineVisible: false,
    })
    featSeries.setData(
      feature.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    )

    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [feature, price])

  return <div ref={ref} className="chart" />
}

export default function Features() {
  const [meta, setMeta] = useState<FeaturesMeta | null>(null)
  const [name, setName] = useState('vol_20d')
  const [rangeDays, setRangeDays] = useState<number | null>(3 * 365)
  const [series, setSeries] = useState<Point[]>([])
  const [price, setPrice] = useState<Bar[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/data/features')
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setMeta)
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    const startParam =
      rangeDays != null
        ? `?start=${new Date(Date.now() - rangeDays * 86400_000).toISOString().slice(0, 10)}`
        : ''
    fetch(`/api/data/features/${name}${startParam}`)
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setSeries)
      .catch((e) => setError(String(e)))
    fetch(`/api/data/bars/XAU?timeframe=D${startParam.replace('?', '&')}`)
      .then((r) => r.json())
      .then(setPrice)
      .catch((e) => setError(String(e)))
  }, [name, rangeDays])

  if (error) {
    return (
      <div className="container">
        <div className="card error">{error}</div>
      </div>
    )
  }
  if (!meta) return <div className="container muted">Calculando features…</div>

  return (
    <div className="container wide">
      <header>
        <h1>Features técnicas</h1>
        <p className="muted">
          Calculadas sin leakage: solo información disponible al cierre de cada día ·
          último dato {meta.latest_date}
        </p>
      </header>

      <div className="toolbar">
        <select className="select" value={name} onChange={(e) => setName(e.target.value)}>
          {meta.names.map((n) => (
            <option key={n} value={n}>
              {n} — {meta.descriptions[n] ?? ''}
            </option>
          ))}
        </select>
        <div className="seg">
          {RANGES.map((r) => (
            <button
              key={r.label}
              className={`seg-btn ${r.days === rangeDays ? 'seg-active' : ''}`}
              onClick={() => setRangeDays(r.days)}
            >
              {r.label}
            </button>
          ))}
        </div>
        <span className="muted small">
          azul: feature (escala izq.) · dorado: XAU (escala dcha.)
        </span>
      </div>

      <div className="card chart-card">
        {series.length > 0 ? (
          <FeatureChart feature={series} price={price} />
        ) : (
          <p className="muted">Sin datos para esta feature en el rango.</p>
        )}
      </div>

      <h2>Snapshot — {meta.latest_date}</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Feature</th>
              <th>Valor actual</th>
              <th>Descripción</th>
            </tr>
          </thead>
          <tbody>
            {meta.names.map((n) => (
              <tr
                key={n}
                onClick={() => setName(n)}
                className={n === name ? 'row-active' : 'row-click'}
              >
                <td>
                  <code>{n}</code>
                </td>
                <td>{meta.latest[n] ?? '—'}</td>
                <td className="muted">{meta.descriptions[n] ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
