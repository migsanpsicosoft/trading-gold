import { useEffect, useRef, useState } from 'react'
import { LineSeries, createChart, type UTCTimestamp } from 'lightweight-charts'

interface Point {
  time: number
  value: number
}
interface Run {
  ts: string
  exposure: number
  price: number
  balance: number
  currency: string
  held_units: number
  target_units: number
  order_units: number
  dry_run: boolean
}
interface LiveResponse {
  runs: Run[]
  live_equity: Point[]
  backtest_equity: Point[]
}

interface ShadowBook {
  days: number
  virtual_return: number | null
  equity: Point[]
  latest_exposures: Record<string, number>
}
interface ShadowResponse {
  books: Record<string, ShadowBook>
  days_tracked: number
}

function TrackingChart({ live, backtest }: { live: Point[]; backtest: Point[] }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || live.length === 0) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: '#161b22' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      timeScale: { borderColor: '#30363d' },
      rightPriceScale: { borderColor: '#30363d' },
    })
    const bt = chart.addSeries(LineSeries, {
      color: '#8b949e',
      lineWidth: 1,
      priceLineVisible: false,
    })
    bt.setData(backtest.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })))
    const lv = chart.addSeries(LineSeries, {
      color: '#d4a017',
      lineWidth: 2,
      priceLineVisible: false,
    })
    lv.setData(live.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [live, backtest])

  return <div ref={ref} className="chart" />
}

function ShadowSection({ shadow }: { shadow: ShadowResponse }) {
  const names: Record<string, string> = {
    multi_full: 'Multi completo (9 libros, backtest 0.51)',
    top10: 'Selección top10 (backtest no creíble — la sombra la juzga)',
  }
  return (
    <>
      <h2>Libros sombra (sin órdenes) — {shadow.days_tracked} días acumulados</h2>
      <div className="metrics">
        {Object.entries(shadow.books).map(([key, book]) => (
          <div key={key} className="card metric">
            <span className="metric-label">{names[key] ?? key}</span>
            <span className="metric-value">
              {book.virtual_return == null
                ? 'acumulando…'
                : `${(book.virtual_return * 100).toFixed(2)}% virtual`}
            </span>
            <span className="muted small">
              {Object.entries(book.latest_exposures)
                .filter(([, v]) => Math.abs(v) > 0.001)
                .map(([a, v]) => `${a} ${(v * 100).toFixed(0)}%`)
                .join(' · ') || 'plano'}
            </span>
          </div>
        ))}
      </div>
    </>
  )
}

export default function Live() {
  const [data, setData] = useState<LiveResponse | null>(null)
  const [shadow, setShadow] = useState<ShadowResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/live')
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setData)
      .catch((e) => setError(String(e)))
    fetch('/api/shadow')
      .then((r) => r.json())
      .then(setShadow)
      .catch(() => {})
  }, [])

  if (error) {
    return (
      <div className="container">
        <div className="card error">{error}</div>
      </div>
    )
  }
  if (!data) return <div className="container muted">Cargando…</div>

  if (data.runs.length === 0) {
    return (
      <div className="container">
        <header>
          <h1>Paper trading (Fase 7)</h1>
          <p className="muted">Aún no hay ejecuciones registradas</p>
        </header>
        <div className="card">
          <h2>Puesta en marcha</h2>
          <ol style={{ lineHeight: 2 }}>
            <li>
              Crea una cuenta demo en <strong>oanda.com</strong> (fxTrade Practice),
              balance recomendado <strong>50.000€</strong>.
            </li>
            <li>
              Genera el API key en <em>Mi cuenta → Manage API Access</em> y copia el
              Account ID (formato <code>101-004-XXXXXXX-001</code>).
            </li>
            <li>
              Pega ambos en el <code>.env</code> (plantilla en{' '}
              <code>.env.example</code>).
            </li>
            <li>
              Primera prueba sin operar:{' '}
              <code>python -m gold_bot.execution.daily_run --dry-run</code>
            </li>
            <li>
              Cuando el dry-run cuadre, programa la ejecución nocturna (el comando
              exacto está en el README, sección Fase 7).
            </li>
          </ol>
        </div>
        {shadow && Object.keys(shadow.books).length > 0 && (
          <ShadowSection shadow={shadow} />
        )}
      </div>
    )
  }

  const last = data.runs[0]

  return (
    <div className="container wide">
      <header>
        <h1>Paper trading — live vs backtest</h1>
        <p className="muted">
          Dorado: cuenta OANDA practice · gris: backtest teórico desde el mismo día ·
          la divergencia entre ambos ES la métrica de la Fase 7
        </p>
      </header>

      <div className="metrics">
        <div className="card metric">
          <span className="metric-label">Última ejecución</span>
          <span className="metric-value">{last.ts.slice(0, 16).replace('T', ' ')}</span>
          <span className="muted small">{last.dry_run ? 'dry-run' : 'orden real'}</span>
        </div>
        <div className="card metric">
          <span className="metric-label">Balance</span>
          <span className="metric-value">
            {last.balance.toLocaleString()} {last.currency}
          </span>
          <span className="muted small">{data.runs.length} ejecuciones registradas</span>
        </div>
        <div className="card metric">
          <span className="metric-label">Posición / objetivo</span>
          <span className="metric-value">
            {last.held_units} → {last.target_units} oz
          </span>
          <span className="muted small">
            exposición {(last.exposure * 100).toFixed(1)}% · XAU {last.price.toFixed(0)}$
          </span>
        </div>
      </div>

      <h2>Equity normalizada desde el inicio del paper trading</h2>
      <div className="card chart-card">
        <TrackingChart live={data.live_equity} backtest={data.backtest_equity} />
      </div>

      {shadow && Object.keys(shadow.books).length > 0 && (
        <ShadowSection shadow={shadow} />
      )}

      <h2>Registro de ejecuciones</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Exposición</th>
              <th>Objetivo</th>
              <th>Orden</th>
              <th>Balance</th>
              <th>Modo</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.slice(0, 20).map((r) => (
              <tr key={r.ts}>
                <td className="muted">{r.ts.slice(0, 16).replace('T', ' ')}</td>
                <td>{(r.exposure * 100).toFixed(1)}%</td>
                <td>{r.target_units} oz</td>
                <td>{r.order_units !== 0 ? `${r.order_units > 0 ? '+' : ''}${r.order_units} oz` : '—'}</td>
                <td>
                  {r.balance.toLocaleString()} {r.currency}
                </td>
                <td>{r.dry_run ? '🧪 dry' : '✅ real'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
