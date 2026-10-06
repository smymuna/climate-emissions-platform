import { fireEvent, render, screen } from '@testing-library/react'
import type { CountryYearIndicator } from '../api/types'
import { ChangeRanking } from './ChangeRanking'

const row = (country: string, name: string, change: number | null): CountryYearIndicator => ({
  country,
  name,
  year: 2024,
  total_ghg_mt: 1,
  emissions_source: 'eurostat',
  population: 1,
  population_source: 'worldbank',
  ghg_per_capita_t: 1,
  change_vs_1990_pct: change,
  change_vs_prev_year_pct: null,
})

describe('ChangeRanking', () => {
  const rows = [row('DE', 'Germany', -48.1), row('CY', 'Cyprus', 58.3), row('EE', 'Estonia', -74.6), row('XX', 'Nowhere', null)]

  it('orders countries from largest cut to largest increase', () => {
    render(<ChangeRanking rows={rows} selected="DE" onSelect={() => {}} />)
    const rowsEls = screen.getAllByRole('row') as HTMLTableRowElement[]
    const names = rowsEls.slice(1).map((r) => r.cells[0].textContent)
    expect(names).toEqual(['Estonia', 'Germany', 'Cyprus'])
  })

  it('says how many countries are missing instead of hiding them silently', () => {
    render(<ChangeRanking rows={rows} selected="DE" onSelect={() => {}} />)
    expect(screen.getByText(/1 country has no 1990 value/)).toBeInTheDocument()
  })

  it('selects a country on click', () => {
    const onSelect = vi.fn()
    render(<ChangeRanking rows={rows} selected="DE" onSelect={onSelect} />)
    fireEvent.click(screen.getByLabelText('Cyprus +58.3%'))
    expect(onSelect).toHaveBeenCalledWith('CY')
  })
})
