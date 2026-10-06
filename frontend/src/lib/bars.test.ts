import { barPath } from './bars'

describe('barPath', () => {
  it('is square at the baseline and rounded at the data end', () => {
    const d = barPath(10, 0, 100, 16)
    expect(d.startsWith('M10,0H106')).toBe(true) // straight edge from the baseline, 4px radius
    expect(d).toContain('Q110,0 110,4')
    expect(d.endsWith('H10Z')).toBe(true)
  })

  it('draws nothing for an empty bar', () => {
    expect(barPath(0, 0, 0, 16)).toBe('')
  })
})
