const nf = (digits: number) =>
  new Intl.NumberFormat('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export function formatMt(value: number | null | undefined): string {
  if (value == null) return '–'
  if (Math.abs(value) >= 100) return `${nf(0).format(value)} Mt`
  if (Math.abs(value) >= 1) return `${nf(1).format(value)} Mt`
  return `${nf(2).format(value)} Mt`
}

export function formatPct(value: number | null | undefined, signed = true): string {
  if (value == null) return '–'
  const s = nf(1).format(Math.abs(value))
  if (!signed || value === 0) return `${value < 0 ? '−' : ''}${s}%`
  return `${value > 0 ? '+' : '−'}${s}%`
}

export function formatInt(value: number | null | undefined): string {
  return value == null ? '–' : nf(0).format(value)
}

export function formatCompact(value: number): string {
  return new Intl.NumberFormat('en-GB', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  )
}

export const SOURCE_LABEL: Record<string, string> = {
  eurostat: 'Eurostat',
  worldbank: 'World Bank',
  owid: 'Our World in Data',
}
