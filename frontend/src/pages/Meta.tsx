import { useEffect, useState } from 'react'

interface Importance {
  feature: string
  gain_pct: number
}
interface Uplift {
  strategy: string
  sharpe_before: number | null
  sharpe_after: number | null
  signals_evaluated: number
  signals_taken_pct: number | null
}
interface Decision {
  date: string
  strategy: string
  side: number
  prob: number | null
  taken: boolean
  outcome: number
}
interface MetaResponse {
  config: { refit_freq: string; train_window_days: number | null; threshold: number }
  n_samples: number
  base_rate: number
  cv_auc: { folds: number[]; mean: number }
  wf_auc: number | null
  signals_taken_pct: number
  importance: Importance[]
  uplift: Uplift[]
  recent_decisions: Decision[]
}

const fmt = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toFixed(d))

export default function Meta() {
  const [data, setData] = useState<MetaResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/meta')
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
        Entrenando meta-modelo walk-forward (la primera vez tarda 1-2 minutos)…
      </div>
    )
  }

  const maxGain = data.importance[0]?.gain_pct ?? 1

  return (
    <div className="container wide">
      <header>
        <h1>Meta-modelo (XGBoost)</h1>
        <p className="muted">
          Meta-labeling: no predice el mercado — predice si cada señal de cada
          estrategia va a funcionar · walk-forward{' '}
          {data.config.refit_freq === 'QE' ? 'trimestral' : 'anual'} · ventana{' '}
          {data.config.train_window_days == null
            ? 'expansiva'
            : `${data.config.train_window_days} días`}
        </p>
      </header>

      <div className="metrics">
        <div className="card metric">
          <span className="metric-label">AUC (CV purgado, 5 folds)</span>
          <span className="metric-value">{fmt(data.cv_auc.mean, 3)}</span>
          <span className="muted small">folds: {data.cv_auc.folds.join(' · ')}</span>
        </div>
        <div className="card metric">
          <span className="metric-label">AUC walk-forward</span>
          <span className="metric-value">{fmt(data.wf_auc, 3)}</span>
          <span className="muted small">0.5 = moneda al aire</span>
        </div>
        <div className="card metric">
          <span className="metric-label">Señales</span>
          <span className="metric-value">{data.n_samples.toLocaleString()}</span>
          <span className="muted small">
            base rate {fmt(data.base_rate, 3)} · toma el{' '}
            {(data.signals_taken_pct * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      <h2>Uplift por estrategia (Sharpe OOS antes → después del filtro)</h2>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Estrategia</th>
              <th>Antes</th>
              <th>Después</th>
              <th>Δ</th>
              <th>Señales evaluadas</th>
              <th>% tomadas</th>
            </tr>
          </thead>
          <tbody>
            {data.uplift.map((u) => {
              const delta =
                u.sharpe_before != null && u.sharpe_after != null
                  ? u.sharpe_after - u.sharpe_before
                  : null
              return (
                <tr key={u.strategy}>
                  <td>
                    <code>{u.strategy}</code>
                  </td>
                  <td>{fmt(u.sharpe_before)}</td>
                  <td>{fmt(u.sharpe_after)}</td>
                  <td
                    style={{
                      color:
                        delta == null ? undefined : delta >= 0 ? '#3fb950' : '#f85149',
                    }}
                  >
                    {delta == null ? '—' : (delta >= 0 ? '+' : '') + delta.toFixed(2)}
                  </td>
                  <td>{u.signals_evaluated.toLocaleString()}</td>
                  <td>
                    {u.signals_taken_pct == null
                      ? '—'
                      : `${(u.signals_taken_pct * 100).toFixed(0)}%`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="columns">
        <section>
          <h2>Qué mira el modelo (importancia por gain)</h2>
          <div className="card">
            {data.importance.map((f) => (
              <div key={f.feature} className="imp-row">
                <code className="imp-name">{f.feature}</code>
                <div className="imp-bar-track">
                  <div
                    className="imp-bar"
                    style={{ width: `${(f.gain_pct / maxGain) * 100}%` }}
                  />
                </div>
                <span className="muted small">{(f.gain_pct * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2>Últimas decisiones</h2>
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Estrategia</th>
                  <th>P(éxito)</th>
                  <th>Decisión</th>
                  <th>Resultado</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_decisions.slice(-15).reverse().map((d, i) => (
                  <tr key={i}>
                    <td className="muted">{d.date}</td>
                    <td>
                      <code>{d.strategy}</code> {d.side > 0 ? '▲' : '▼'}
                    </td>
                    <td>{d.prob == null ? '—' : d.prob.toFixed(2)}</td>
                    <td>{d.taken ? '✅ tomar' : '⛔ saltar'}</td>
                    <td>{d.outcome === 1 ? '✓ ganó' : '✗ perdió'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  )
}
