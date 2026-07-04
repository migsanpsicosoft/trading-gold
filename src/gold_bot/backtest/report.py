"""Artefacto HTML por backtest (regla de reproducibilidad del proyecto).

Cada informe es autocontenido y auditable: métricas por capa, DSR,
stress tests, equity/drawdown en SVG inline, y la caja de
reproducibilidad — content-hashes de los datasets, commit de git,
seed y parámetros. Un resultado sin su informe no existe.
"""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from gold_bot.config import PROJECT_ROOT, settings

REPORTS_DIR = settings.data_dir / "reports"


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, cwd=PROJECT_ROOT,
                             timeout=10)
        return out.stdout.strip() or "desconocido"
    except Exception:
        return "desconocido"


def _svg_line(series: pd.Series, width: int = 860, height: int = 240,
              color: str = "#d4a017") -> str:
    """Polilínea SVG de una serie (sin dependencias de plotting)."""
    s = series.dropna()
    if len(s) < 2:
        return "<svg/>"
    values = s.to_numpy(dtype=float)
    lo, hi = values.min(), values.max()
    span = (hi - lo) or 1.0
    xs = np.linspace(0, width, len(values))
    ys = height - (values - lo) / span * (height - 20) - 10
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    y0 = float(height - (0 - lo) / span * (height - 20) - 10) if lo < 0 < hi else None
    zero_line = (f'<line x1="0" y1="{y0:.1f}" x2="{width}" y2="{y0:.1f}" '
                 f'stroke="#30363d" stroke-dasharray="4"/>') if y0 else ""
    first, last = s.index[0].date(), s.index[-1].date()
    return (
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;background:#161b22">'
        f"{zero_line}"
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{points}"/>'
        f'<text x="4" y="{height - 4}" fill="#8b949e" font-size="11">{first}</text>'
        f'<text x="{width - 80}" y="{height - 4}" fill="#8b949e" font-size="11">{last}</text>'
        "</svg>"
    )


def _metrics_rows(layers: dict[str, dict]) -> str:
    rows = []
    for name, m in layers.items():
        rows.append(
            f"<tr><td>{name}</td><td>{m.get('sharpe', float('nan')):.2f}</td>"
            f"<td>{m.get('cagr', 0) * 100:.1f}%</td>"
            f"<td>{m.get('max_drawdown', 0) * 100:.1f}%</td>"
            f"<td>{m.get('vol', 0) * 100:.1f}%</td></tr>"
        )
    return "".join(rows)


def build_report(final_returns: pd.Series, layers: dict[str, dict],
                 dsr: dict, stress: dict, data_hashes: list[dict],
                 params: dict) -> Path:
    """Genera el HTML y devuelve su ruta."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    path = REPORTS_DIR / f"backtest_{now.strftime('%Y%m%d_%H%M%S')}.html"

    equity = np.exp(final_returns.fillna(0).cumsum())
    dd = equity / equity.cummax() - 1

    hashes_rows = "".join(
        f"<tr><td><code>{h['symbol']}</code></td><td><code>{h['hash']}</code></td></tr>"
        for h in data_hashes
    )
    episodes_rows = "".join(
        f"<tr><td>{e['start']}</td><td>{e['depth'] * 100:.1f}%</td>"
        f"<td>{e['days_to_trough']}</td>"
        f"<td>{e['days_to_recover'] if e['days_to_recover'] is not None else 'en curso'}</td></tr>"
        for e in stress["episodes"]
    )
    crisis_rows = "".join(
        f"<tr><td>{c['name']}</td><td>{c['period']}</td>"
        f"<td>{c['return'] * 100:+.1f}%</td><td>{c['max_dd'] * 100:.1f}%</td></tr>"
        for c in stress["crisis"]
    )
    params_rows = "".join(
        f"<tr><td><code>{k}</code></td><td>{v}</td></tr>" for k, v in params.items()
    )

    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Backtest gold-hybrid-bot — {now.strftime('%Y-%m-%d %H:%M')} UTC</title>
<style>
body{{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',sans-serif;
max-width:920px;margin:2rem auto;padding:0 1rem}}
h1{{font-size:1.4rem}} h2{{font-size:1.05rem;margin-top:2rem;color:#d4a017}}
table{{width:100%;border-collapse:collapse;font-size:.9rem}}
td,th{{padding:.35rem .6rem;border-bottom:1px solid #30363d;text-align:left}}
th{{color:#8b949e}} code{{color:#d4a017}}
.muted{{color:#8b949e;font-size:.85rem}}
.box{{background:#161b22;border:1px solid #30363d;border-radius:8px;
padding:1rem;margin:.8rem 0}}
</style></head><body>
<h1>🥇 gold-hybrid-bot — informe de backtest</h1>
<p class="muted">Generado {now.isoformat()} · commit <code>{_git_commit()}</code>
· seed {settings.random_seed} · walk-forward de punta a punta con costes reales</p>

<h2>Métricas por capa (OOS 2019-hoy)</h2>
<div class="box"><table>
<tr><th>Capa</th><th>Sharpe</th><th>CAGR</th><th>Max DD</th><th>Vol</th></tr>
{_metrics_rows(layers)}</table></div>

<h2>Deflated Sharpe Ratio</h2>
<div class="box"><p>DSR = <strong>{dsr['dsr']:.3f}</strong> — probabilidad de que
el Sharpe {dsr['sharpe_annual']:.2f} sea skill y no el mejor de
{dsr['n_trials']} intentos (benchmark del máximo esperado por suerte:
{dsr['sr0_annual_equiv']:.2f}). Skew {dsr['skew']:.2f} ·
curtosis {dsr['kurtosis']:.1f} · {dsr['days']} días.</p></div>

<h2>Equity (cartera final)</h2>
<div class="box">{_svg_line(equity)}</div>
<h2>Drawdown</h2>
<div class="box">{_svg_line(dd, color="#f85149")}</div>

<h2>Peores episodios de drawdown</h2>
<div class="box"><table>
<tr><th>Inicio</th><th>Profundidad</th><th>Días a valle</th><th>Días a recuperar</th></tr>
{episodes_rows}</table></div>

<h2>Ventanas de crisis</h2>
<div class="box"><table>
<tr><th>Evento</th><th>Periodo</th><th>Retorno</th><th>Max DD</th></tr>
{crisis_rows}</table></div>

<h2>Reproducibilidad — datasets exactos</h2>
<div class="box"><table>
<tr><th>Dataset</th><th>sha256</th></tr>{hashes_rows}</table></div>

<h2>Parámetros</h2>
<div class="box"><table>{params_rows}</table></div>
</body></html>"""

    path.write_text(html, encoding="utf-8")
    return path
