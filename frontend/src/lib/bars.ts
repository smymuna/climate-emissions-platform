/** Horizontal bar path: square at the baseline, 4px rounded data end. */
export function barPath(x0: number, y0: number, w: number, h: number, r = 4): string {
  if (w <= 0) return ''
  const rr = Math.min(r, w, h / 2)
  return `M${x0},${y0}H${x0 + w - rr}Q${x0 + w},${y0} ${x0 + w},${y0 + rr}V${y0 + h - rr}Q${x0 + w},${y0 + h} ${x0 + w - rr},${y0 + h}H${x0}Z`
}
