/** Minimal linear scale and "nice" ticks; enough for these charts without a chart library. */

export type Scale = ((v: number) => number) & { domain: [number, number]; range: [number, number] }

export function linearScale(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain
  const [r0, r1] = range
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0)
  const f = ((v: number) => r0 + (v - d0) * k) as Scale
  f.domain = domain
  f.range = range
  return f
}

/** Round step sizes: 1, 2, 2.5, 5 × 10^n, giving about `count` ticks. */
export function niceStep(span: number, count: number): number {
  if (span <= 0 || !Number.isFinite(span)) return 1
  const raw = span / Math.max(1, count)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10
  return nice * mag
}

/** Ticks covering [min, max], starting and ending on multiples of a nice step. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (min === max) {
    const pad = Math.abs(min) || 1
    return niceTicks(min - pad, max + pad, count)
  }
  const step = niceStep(max - min, count)
  const start = Math.floor(min / step) * step
  const end = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toFixed(10)))
  return ticks
}
