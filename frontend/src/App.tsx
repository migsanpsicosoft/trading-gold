import { useEffect, useState } from 'react'

// --- Tipos que devuelve GET /api/status (espejo del backend) ---
interface RoadmapItem {
  done: boolean
  text: string
}
interface Phase {
  title: string
  items: RoadmapItem[]
}
interface Module {
  name: string
  description: string
  exists: boolean
}
interface DataDir {
  name: string
  files: number
}
interface Status {
  version: string
  current_phase: string | null
  phases: Phase[]
  modules: Module[]
  data_dirs: DataDir[]
  random_seed: number
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress">
      <div className="progress-fill" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  )
}

function PhaseCard({ phase, isCurrent }: { phase: Phase; isCurrent: boolean }) {
  const done = phase.items.filter((i) => i.done).length
  const total = phase.items.length
  const complete = total > 0 && done === total
  const [open, setOpen] = useState(isCurrent)

  return (
    <div className={`card phase ${isCurrent ? 'phase-current' : ''}`}>
      <button className="phase-header" onClick={() => setOpen(!open)}>
        <span className={`dot ${complete ? 'dot-done' : isCurrent ? 'dot-current' : ''}`} />
        <span className="phase-title">{phase.title}</span>
        <span className="phase-count">
          {done}/{total}
        </span>
      </button>
      <ProgressBar value={total ? done / total : 0} />
      {open && (
        <ul className="phase-items">
          {phase.items.map((item) => (
            <li key={item.text} className={item.done ? 'item-done' : ''}>
              <span className="check">{item.done ? '✓' : '○'}</span> {item.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/status')
      .then((r) => {
        if (!r.ok) throw new Error(`API respondió ${r.status}`)
        return r.json()
      })
      .then(setStatus)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) {
    return (
      <div className="container">
        <div className="card error">
          <strong>No se pudo conectar con el backend.</strong>
          <p>
            Arranca la API con: <code>uvicorn gold_bot.api.main:app --reload --port 8000</code>
          </p>
          <p className="muted">{error}</p>
        </div>
      </div>
    )
  }

  if (!status) return <div className="container muted">Cargando estado del proyecto…</div>

  const totalItems = status.phases.reduce((n, p) => n + p.items.length, 0)
  const doneItems = status.phases.reduce((n, p) => n + p.items.filter((i) => i.done).length, 0)

  return (
    <div className="container">
      <header>
        <h1>
          🥇 Gold Hybrid Bot <span className="version">v{status.version}</span>
        </h1>
        <p className="muted">Sistema híbrido de trading algorítmico en XAU/USD</p>
      </header>

      <div className="metrics">
        <div className="card metric">
          <span className="metric-label">Fase actual</span>
          <span className="metric-value">{status.current_phase ?? '—'}</span>
        </div>
        <div className="card metric">
          <span className="metric-label">Progreso global</span>
          <span className="metric-value">
            {doneItems} / {totalItems} tareas
          </span>
        </div>
        <div className="card metric">
          <span className="metric-label">Seed de reproducibilidad</span>
          <span className="metric-value">{status.random_seed}</span>
        </div>
      </div>

      <div className="columns">
        <section>
          <h2>Fases</h2>
          {status.phases.map((phase) => (
            <PhaseCard
              key={phase.title}
              phase={phase}
              isCurrent={phase.title === status.current_phase}
            />
          ))}
        </section>

        <section>
          <h2>Módulos de gold_bot</h2>
          <p className="muted small">Comprobado contra el filesystem: solo existe lo que existe.</p>
          <div className="card">
            <ul className="modules">
              {status.modules.map((m) => (
                <li key={m.name}>
                  <span className={`badge ${m.exists ? 'badge-ok' : 'badge-pending'}`}>
                    {m.exists ? '✓' : '…'}
                  </span>
                  <code>{m.name}</code>
                  <span className="muted"> — {m.description}</span>
                </li>
              ))}
            </ul>
          </div>

          <h2>Datos locales</h2>
          <div className="card">
            <ul className="modules">
              {status.data_dirs.map((d) => (
                <li key={d.name}>
                  📁 <code>data/{d.name}</code>
                  <span className="muted"> — {d.files} ficheros</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </div>
  )
}
