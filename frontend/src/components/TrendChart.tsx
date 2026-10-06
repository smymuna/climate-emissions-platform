import { useMemo, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { formatMt } from '../lib/format'
import { linearScale, niceTicks } from '../lib/scale'
import { useWidth } from '../lib/useWidth'

export interface Series {
  key: string
  label: string
  color: string // CSS colour, e.g. var(--series-1)
  points: { year: number; value: number }[]
}

interface Props {
  series: Series[]
  height?: number
  title: string
}

const M = { top: 12, right: 110, bottom: 28, left: 52 }
const LABEL_GAP = 14 // minimum vertical distance between end labels

export function TrendChart({ series, height = 300, title }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hoverYear, setHoverYear] = useState<number | null>(null)
  const narrow = width < 520
  const margin = { ...M, right: narrow ? 16 : M.right }

  const { years, x, y, yTicks } = useMemo(() => {
    const all = series.flatMap((s) => s.points)
    const yearsSet = [...new Set(all.map((p) => p.year))].sort((a, b) => a - b)
    const minYear = yearsSet[0] ?? 1990
    const maxYear = yearsSet[yearsSet.length - 1] ?? 2024
    const maxVal = Math.max(1, ...all.map((p) => p.value))
    // Emissions are magnitudes: the axis starts at zero so slopes aren't exaggerated.
    const ticks = niceTicks(0, maxVal, 5)
    return {
      years: yearsSet,
      x: linearScale([minYear, maxYear], [margin.left, width - margin.right]),
      y: linearScale([0, ticks[ticks.length - 1]], [height - M.bottom, M.top]),
      yTicks: ticks,
    }
  }, [series, width, height, margin.left, margin.right])

  const xTicks = useMemo(() => {
    if (!years.length) return []
    const [a, b] = [years[0], years[years.length - 1]]
    const step = width < 520 ? 10 : 5
    const out = []
    for (let yr = Math.ceil(a / step) * step; yr <= b; yr += step) out.push(yr)
    return out
  }, [years, width])

  const path = (pts: Series['points']) => {
    // Break the line at missing years instead of drawing across the gap.
    let d = ''
    let prev: number | null = null
    for (const p of [...pts].sort((a, b) => a.year - b.year)) {
      d += `${prev !== null && p.year === prev + 1 ? 'L' : 'M'}${x(p.year).toFixed(1)},${y(p.value).toFixed(1)}`
      prev = p.year
    }
    return d
  }

  // Direct end labels only when they don't collide; otherwise the legend carries identity.
  const endLabels = useMemo(() => {
    if (narrow) return []
    const ends = series
      .map((s) => {
        const last = [...s.points].sort((a, b) => b.year - a.year)[0]
        return last ? { s, last, py: y(last.value) } : null
      })
      .filter((e): e is NonNullable<typeof e> => e !== null)
      .sort((a, b) => a.py - b.py)
    const clear = ends.every((e, i) => i === 0 || e.py - ends[i - 1].py >= LABEL_GAP)
    return clear ? ends : []
  }, [series, y, narrow])

  const nearestYear = (px: number) => {
    let best: number | null = null
    for (const yr of years) if (best === null || Math.abs(x(yr) - px) < Math.abs(x(best) - px)) best = yr
    return best
  }

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    setHoverYear(nearestYear(e.clientX - box.left))
  }

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (!years.length) return
    const i = hoverYear === null ? years.length - 1 : years.indexOf(hoverYear)
    if (e.key === 'ArrowLeft') setHoverYear(years[Math.max(0, i - 1)])
    else if (e.key === 'ArrowRight') setHoverYear(years[Math.min(years.length - 1, i + 1)])
    else if (e.key === 'Escape') setHoverYear(null)
    else return
    e.preventDefault()
  }

  const hovered =
    hoverYear === null
      ? []
      : series
          .map((s) => ({ s, p: s.points.find((p) => p.year === hoverYear) }))
          .filter((h): h is { s: Series; p: Series['points'][number] } => h.p !== undefined)
  const tipLeft = hoverYear === null ? 0 : x(hoverYear)
  const flip = tipLeft > width - 190

  return (
    <div className="chart" ref={ref}>
      {series.length > 1 && (
        <ul className="legend" aria-label="Legend">
          {series.map((s) => (
            <li key={s.key}>
              <span className="key" style={{ background: s.color }} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${title}. Use left and right arrow keys to read values by year.`}
        tabIndex={0}
        onMouseMove={onMove}
        onMouseLeave={() => setHoverYear(null)}
        onKeyDown={onKey}
        onBlur={() => setHoverYear(null)}
      >
        <g className="axis">
          {yTicks.map((t) => (
            <g key={t}>
              <line
                className={t === 0 ? 'baseline' : 'gridline'}
                x1={margin.left}
                x2={width - margin.right}
                y1={y(t)}
                y2={y(t)}
              />
              <text x={margin.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {t.toLocaleString('en-GB')}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={height - margin.bottom + 18} textAnchor="middle">
              {t}
            </text>
          ))}
        </g>

        {series.map((s) => (
          <path
            key={s.key}
            d={path(s.points)}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}

        {endLabels.map(({ s, last }) => (
          <g key={s.key}>
            <circle cx={x(last.year)} cy={y(last.value)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            <text className="end-label" x={x(last.year) + 10} y={y(last.value)} dy="0.32em">
              {series.length > 1 ? `${s.label}` : formatMt(last.value)}
            </text>
          </g>
        ))}

        {hoverYear !== null && (
          <g>
            <line className="baseline" x1={x(hoverYear)} x2={x(hoverYear)} y1={margin.top} y2={height - margin.bottom} />
            {hovered.map(({ s, p }) => (
              <circle key={s.key} cx={x(p.year)} cy={y(p.value)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        )}
      </svg>

      {hoverYear !== null && hovered.length > 0 && (
        <div
          className="tooltip"
          role="status"
          style={{ top: margin.top + (series.length > 1 ? 34 : 0), left: flip ? tipLeft - 170 : tipLeft + 14 }}
        >
          <div className="t-head">{hoverYear}</div>
          {hovered.map(({ s, p }) => (
            <div className="t-row" key={s.key}>
              <span>
                <span className="key" style={{ background: s.color }} />
                {s.label}
              </span>
              <span className="num">{formatMt(p.value)}</span>
            </div>
          ))}
        </div>
      )}

      <details className="table-view">
        <summary>Show data table</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                {series.map((s) => (
                  <th key={s.key} className="num">
                    {s.label} (Mt)
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...years].reverse().map((yr) => (
                <tr key={yr}>
                  <td>{yr}</td>
                  {series.map((s) => {
                    const v = s.points.find((p) => p.year === yr)?.value
                    return (
                      <td key={s.key} className="num">
                        {v === undefined ? '–' : v.toLocaleString('en-GB', { maximumFractionDigits: 1 })}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
