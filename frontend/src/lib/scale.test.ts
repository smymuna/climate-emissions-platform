import { linearScale, niceStep, niceTicks } from './scale'

describe('linearScale', () => {
  it('maps domain to range, including inverted ranges', () => {
    const y = linearScale([0, 100], [300, 0])
    expect(y(0)).toBe(300)
    expect(y(50)).toBe(150)
    expect(y(100)).toBe(0)
  })

  it('does not divide by zero for a flat domain', () => {
    expect(linearScale([5, 5], [0, 10])(5)).toBe(0)
  })
})

describe('niceTicks', () => {
  it('produces round steps that cover the data', () => {
    expect(niceTicks(0, 1261, 5)).toEqual([0, 500, 1000, 1500])
    expect(niceTicks(0, 640, 5)).toEqual([0, 200, 400, 600, 800])
    expect(niceTicks(-74.6, 58.3, 4)).toEqual([-100, -50, 0, 50, 100])
  })

  it('handles a single value', () => {
    const t = niceTicks(10, 10)
    expect(t[0]).toBeLessThan(10)
    expect(t[t.length - 1]).toBeGreaterThan(10)
  })

  it('picks 1-2-2.5-5 steps', () => {
    expect(niceStep(100, 5)).toBe(20)
    expect(niceStep(1, 4)).toBe(0.25)
    expect(niceStep(0, 4)).toBe(1)
  })
})
