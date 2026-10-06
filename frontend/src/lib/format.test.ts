import { formatMt, formatPct } from './format'

describe('formatMt', () => {
  it('scales decimals with magnitude', () => {
    expect(formatMt(649.77)).toBe('650 Mt')
    expect(formatMt(53.25)).toBe('53.3 Mt')
    expect(formatMt(0.784)).toBe('0.78 Mt')
    expect(formatMt(-41.2)).toBe('-41.2 Mt')
    expect(formatMt(null)).toBe('–')
  })
})

describe('formatPct', () => {
  it('uses a real minus sign and an explicit plus', () => {
    expect(formatPct(-48.1)).toBe('−48.1%')
    expect(formatPct(58.3)).toBe('+58.3%')
    expect(formatPct(0)).toBe('0.0%')
    expect(formatPct(12.5, false)).toBe('12.5%')
    expect(formatPct(undefined)).toBe('–')
  })
})
