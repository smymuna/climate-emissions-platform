import { fireEvent, render, screen, within } from '@testing-library/react'
import { TrendChart, type Series } from './TrendChart'

const one: Series[] = [
  { key: 'a', label: 'Total GHG', color: 'red', points: [{ year: 1990, value: 1250 }, { year: 1991, value: 1200 }] },
]
const three: Series[] = ['Eurostat', 'World Bank', 'Our World in Data'].map((label, i) => ({
  key: label,
  label,
  color: `var(--series-${i + 1})`,
  points: [{ year: 2022, value: 750 - i * 20 }, { year: 2023, value: 670 - i * 20 }],
}))

describe('TrendChart', () => {
  it('has no legend for a single series (the title names it)', () => {
    render(<TrendChart series={one} title="Germany" />)
    expect(screen.queryByLabelText('Legend')).not.toBeInTheDocument()
  })

  it('shows a legend for several series', () => {
    render(<TrendChart series={three} title="Germany" />)
    const legend = screen.getByLabelText('Legend')
    expect(within(legend).getAllByRole('listitem')).toHaveLength(3)
  })

  it('offers every value in a table view', () => {
    render(<TrendChart series={three} title="Germany" />)
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3) // header + 2 years
    expect(within(table).getByText('710')).toBeInTheDocument()
  })

  it('reads values by year with the keyboard', () => {
    render(<TrendChart series={one} title="Germany" />)
    const chart = screen.getByRole('img')
    fireEvent.keyDown(chart, { key: 'ArrowLeft' })
    const tip = screen.getByRole('status')
    expect(tip).toHaveTextContent('1990')
    expect(tip).toHaveTextContent('1,250 Mt')
    fireEvent.keyDown(chart, { key: 'Escape' })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
