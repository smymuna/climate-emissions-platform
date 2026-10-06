import type { SectorShare } from '../api/types'
import { formatMt, formatPct } from '../lib/format'
import { barPath } from '../lib/bars'
import { textWidth } from '../lib/measure'
import { useWidth } from '../lib/useWidth'

const ROW = 30
const BAR = 16 // bars stay thin; the band's leftover is air
const VALUE_W = 110

interface Props {
  sectors: SectorShare[]
}

export function SectorBars({ sectors }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>(480)
  const rows = sectors
    .filter((s) => s.sector !== 'LULUCF' && s.value_mt_co2e > 0)
    .sort((a, b) => b.value_mt_co2e - a.value_mt_co2e)
  const lulucf = sectors.find((s) => s.sector === 'LULUCF')
  // Label column fits the longest name, but never takes more than 40% of the width.
  const longest = Math.max(0, ...rows.map((r) => textWidth(r.name)))
  const labelW = Math.min(Math.ceil(longest) + 12, Math.round(width * 0.4))
  const fits = (name: string) => textWidth(name) + 12 <= labelW
  const max = Math.max(1, ...rows.map((r) => r.value_mt_co2e))
  const plotW = Math.max(40, width - labelW - VALUE_W)
  const height = rows.length * ROW

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="img" aria-label="Emissions by sector, largest first">
        {rows.map((r, i) => {
          const w = (r.value_mt_co2e / max) * plotW
          const y0 = i * ROW + (ROW - BAR) / 2
          return (
            <g key={r.sector}>
              <title>{`${r.name}: ${formatMt(r.value_mt_co2e)} (${formatPct(r.share_pct, false)} of total)`}</title>
              <text className="end-label" x={0} y={y0 + BAR / 2} dy="0.32em">
                {fits(r.name) ? r.name : r.name.split(' ')[0] + '…'}
              </text>
              <path d={barPath(labelW, y0, Math.max(w, 1), BAR)} fill="var(--series-1)" />
              <text className="end-label" x={labelW + w + 8} y={y0 + BAR / 2} dy="0.32em">
                {formatMt(r.value_mt_co2e)}
                {r.share_pct != null && ` · ${formatPct(r.share_pct, false)}`}
              </text>
            </g>
          )
        })}
        <line className="baseline" x1={labelW} x2={labelW} y1={0} y2={height} />
      </svg>
      {lulucf && (
        <p className="subtitle" style={{ marginTop: 10 }}>
          Land use and forestry (LULUCF):{' '}
          <strong>{formatMt(lulucf.value_mt_co2e)}</strong>
          {lulucf.value_mt_co2e < 0 ? ', a net sink, not included in the total.' : ', not included in the total.'}
        </p>
      )}
      <details className="table-view">
        <summary>Show data table</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Sector</th>
                <th className="num">Mt CO₂e</th>
                <th className="num">Share</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map((s) => (
                <tr key={s.sector}>
                  <td>{s.name}</td>
                  <td className="num">{s.value_mt_co2e.toLocaleString('en-GB', { maximumFractionDigits: 2 })}</td>
                  <td className="num">{formatPct(s.share_pct, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
