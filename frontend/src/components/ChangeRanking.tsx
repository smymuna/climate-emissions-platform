import type { CountryYearIndicator } from '../api/types'
import { barPath } from '../lib/bars'
import { formatPct } from '../lib/format'
import { niceTicks } from '../lib/scale'
import { useWidth } from '../lib/useWidth'

const ROW = 22
const BAR = 12
const LABEL_W = 118
const VALUE_ROOM = 52 // space for a value label left of the longest negative bar

interface Props {
  rows: CountryYearIndicator[]
  selected: string
  onSelect: (iso2: string) => void
}

/** Change vs 1990 for every country: cuts go left (blue), increases go right (red). */
export function ChangeRanking({ rows, selected, onSelect }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(480)
  const data = rows
    .filter((r) => r.change_vs_1990_pct != null)
    .sort((a, b) => (a.change_vs_1990_pct as number) - (b.change_vs_1990_pct as number))
  const missing = rows.length - data.length
  const values = data.map((d) => d.change_vs_1990_pct as number)
  const ticks = niceTicks(Math.min(0, ...values), Math.max(0, ...values), width < 520 ? 2 : 4)
  const [lo, hi] = [ticks[0], ticks[ticks.length - 1]]
  const plotL = LABEL_W + 8 + (values.some((v) => v < 0) ? VALUE_ROOM : 0)
  const plotR = width - 56
  const x = (v: number) => plotL + ((v - lo) / (hi - lo)) * (plotR - plotL)
  const height = data.length * ROW + 22

  return (
    <div className="chart" ref={ref}>
      <ul className="legend" aria-label="Legend">
        <li>
          <span className="key" style={{ background: 'var(--decrease)' }} />
          Lower than 1990
        </li>
        <li>
          <span className="key" style={{ background: 'var(--increase)' }} />
          Higher than 1990
        </li>
      </ul>
      <svg width={width} height={height} role="img" aria-label="Change in emissions since 1990 by country">
        {ticks.map((t) => (
          <g key={t} className="axis">
            <line className={t === 0 ? 'baseline' : 'gridline'} x1={x(t)} x2={x(t)} y1={0} y2={height - 22} />
            <text x={x(t)} y={height - 6} textAnchor="middle">
              {t > 0 ? `+${t}%` : `${t}%`}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const v = d.change_vs_1990_pct as number
          const y0 = i * ROW + (ROW - BAR) / 2
          const isSel = d.country === selected
          const w = Math.abs(x(v) - x(0))
          // Mirror the bar for negative values so the rounded end is always the data end.
          const transform = v < 0 ? `translate(${2 * x(0)},0) scale(-1,1)` : undefined
          return (
            <g
              key={d.country}
              onClick={() => onSelect(d.country)}
              style={{ cursor: 'pointer' }}
              aria-label={`${d.name} ${formatPct(v)}`}
            >
              <title>{`${d.name}: ${formatPct(v)} vs 1990 (${d.emissions_source})`}</title>
              <rect x={0} y={i * ROW} width={width} height={ROW} fill={isSel ? 'var(--accent-soft)' : 'transparent'} />
              <text className="end-label" x={LABEL_W} y={y0 + BAR / 2} dy="0.32em" textAnchor="end" fontWeight={isSel ? 700 : 400}>
                {d.name}
              </text>
              <path d={barPath(x(0), y0, Math.max(w, 1), BAR)} transform={transform} fill={v < 0 ? 'var(--decrease)' : 'var(--increase)'} />
              {(isSel || i === 0 || i === data.length - 1 || v > 0) && (
                <text className="end-label" x={v < 0 ? x(v) - 6 : x(v) + 6} y={y0 + BAR / 2} dy="0.32em" textAnchor={v < 0 ? 'end' : 'start'}>
                  {formatPct(v)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {missing > 0 && (
        <p className="subtitle" style={{ marginTop: 8 }}>
          {missing} {missing === 1 ? 'country has' : 'countries have'} no 1990 value in the preferred source and {missing === 1 ? 'is' : 'are'} not shown.
        </p>
      )}
      <details className="table-view">
        <summary>Show data table</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Country</th>
                <th className="num">Change vs 1990</th>
                <th className="num">t CO₂e / person</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.country} className={d.country === selected ? 'selected' : undefined}>
                  <td>{d.name}</td>
                  <td className="num">{formatPct(d.change_vs_1990_pct)}</td>
                  <td className="num">{d.ghg_per_capita_t?.toFixed(1) ?? '–'}</td>
                  <td>{d.emissions_source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
