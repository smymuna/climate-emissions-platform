import type { Reconciliation, Run } from '../api/types'
import { formatInt, formatPct, SOURCE_LABEL } from '../lib/format'

const STATUS = {
  succeeded: { color: 'var(--status-good)', label: 'Succeeded', icon: '✓' },
  failed: { color: 'var(--status-critical)', label: 'Failed', icon: '✕' },
  running: { color: 'var(--status-warning)', label: 'Running', icon: '…' },
} as const

function latestPerSource(runs: Run[]): Run[] {
  const seen = new Map<string, Run>()
  for (const r of runs) if (!seen.has(r.source)) seen.set(r.source, r) // runs come newest first
  return [...seen.values()]
}

interface Props {
  runs: Run[]
  reconciliation: Reconciliation[]
  year: number
  selected: string
  countryNames: Record<string, string>
}

export function QualityPanel({ runs, reconciliation, year, selected, countryNames }: Props) {
  const latest = latestPerSource(runs)
  const recon = reconciliation.filter((r) => r.n_sources >= 2)
  const over10 = recon.filter((r) => (r.spread_pct ?? 0) > 10).length

  return (
    <div className="grid two">
      <div className="card">
        <h2>Latest ingestion runs</h2>
        <p className="subtitle">Each run records what was dropped, rejected or flagged.</p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Status</th>
                <th className="num">Parsed</th>
                <th className="num">Loaded</th>
                <th className="num">Rejected</th>
                <th className="num" title="Warnings">Warn.</th>
              </tr>
            </thead>
            <tbody>
              {latest.map((r) => {
                const s = STATUS[r.status]
                return (
                  <tr key={r.id}>
                    <td>{SOURCE_LABEL[r.source] ?? r.source}</td>
                    <td>
                      <span className="status">
                        <span className="status-dot" style={{ background: s.color }} aria-hidden="true" />
                        <span aria-hidden="true">{s.icon}</span> {s.label}
                      </span>
                    </td>
                    <td className="num">{formatInt(r.records_parsed)}</td>
                    <td className="num">{formatInt(r.records_valid)}</td>
                    <td className="num">{formatInt(r.records_rejected)}</td>
                    <td className="num">{formatInt(r.quality?.warnings_total)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {latest[0] && (
          <p className="subtitle" style={{ marginTop: 10 }}>
            Last run: {new Date(latest[0].started_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}
          </p>
        )}
      </div>

      <div className="card">
        <h2>Do the sources agree? ({year})</h2>
        <p className="subtitle">
          Total GHG excl. LULUCF. The gap between sources is above 10% for {over10} of {recon.length} countries,
          mostly due to different methods.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Country</th>
                <th className="num">Eurostat</th>
                <th className="num">World Bank</th>
                <th className="num">OWID</th>
                <th className="num">Spread</th>
              </tr>
            </thead>
            <tbody>
              {recon.map((r) => (
                <tr key={r.country} className={r.country === selected ? 'selected' : undefined}>
                  <td>{countryNames[r.country] ?? r.country}</td>
                  <td className="num">{r.eurostat_mt?.toFixed(1) ?? '–'}</td>
                  <td className="num">{r.worldbank_mt?.toFixed(1) ?? '–'}</td>
                  <td className="num">{r.owid_mt?.toFixed(1) ?? '–'}</td>
                  <td className="num">{formatPct(r.spread_pct, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
