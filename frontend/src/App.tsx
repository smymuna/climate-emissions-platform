import { useEffect, useMemo, useState } from 'react'
import { API_URL } from './api/client'
import {
  SOURCE_ORDER,
  useCountries,
  useCountryIndicators,
  useReconciliation,
  useRuns,
  useSectors,
  useSourceSeries,
  useYearIndicators,
} from './api/hooks'
import { ChangeRanking } from './components/ChangeRanking'
import { QualityPanel } from './components/QualityPanel'
import { SectorBars } from './components/SectorBars'
import { StatTile } from './components/StatTile'
import { TrendChart, type Series } from './components/TrendChart'
import { formatMt, formatPct, SOURCE_LABEL } from './lib/format'

const REPO = 'https://github.com/smymuna/climate-emissions-platform'
const SOURCE_COLOR: Record<string, string> = {
  eurostat: 'var(--series-1)',
  worldbank: 'var(--series-2)',
  owid: 'var(--series-3)',
}

function initialCountry(): string {
  const fromUrl = new URLSearchParams(window.location.search).get('country')
  return fromUrl && /^[A-Za-z]{2}$/.test(fromUrl) ? fromUrl.toUpperCase() : 'DE'
}

/** Free hosting sleeps when idle; say so instead of showing an endless spinner. */
function useSlow(loading: boolean, ms = 4000) {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!loading) return
    const t = setTimeout(() => setSlow(true), ms)
    return () => clearTimeout(t)
  }, [loading, ms])
  return loading && slow
}

function toggleTheme() {
  const root = document.documentElement
  const dark = root.dataset.theme
    ? root.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches
  root.dataset.theme = dark ? 'light' : 'dark'
  try {
    localStorage.setItem('theme', root.dataset.theme)
  } catch {
    // storage unavailable (private mode); the toggle still works for this visit
  }
}

export default function App() {
  const [country, setCountry] = useState(initialCountry)
  const [compare, setCompare] = useState(false)

  useEffect(() => {
    const url = new URL(window.location.href)
    url.searchParams.set('country', country)
    window.history.replaceState(null, '', url)
  }, [country])

  const countries = useCountries()
  const indicators = useCountryIndicators(country)
  const latestAll = useYearIndicators()
  const sourceSeries = useSourceSeries(country, compare)
  const runs = useRuns()

  const series = useMemo(() => indicators.data?.series ?? [], [indicators.data])
  const latest = series[series.length - 1]
  const sectorYear = latest?.year
  const sectors = useSectors(country, sectorYear)
  const reconYear = latestAll.data ? latestAll.data.year - 2 : undefined // all three sources overlap
  const reconciliation = useReconciliation(reconYear)

  const slow = useSlow(countries.isLoading || indicators.isLoading)
  const names = useMemo(
    () => Object.fromEntries((countries.data ?? []).map((c) => [c.iso2, c.name])),
    [countries.data],
  )
  const countryName = names[country] ?? country

  const chartSeries: Series[] = useMemo(() => {
    if (!compare) {
      return [
        {
          key: 'preferred',
          label: 'Total GHG',
          color: 'var(--series-1)',
          points: series.map((p) => ({ year: p.year, value: p.total_ghg_mt })),
        },
      ]
    }
    return SOURCE_ORDER.map((code, i) => ({
      key: code,
      label: SOURCE_LABEL[code],
      color: SOURCE_COLOR[code],
      points: (sourceSeries[i]?.data?.data ?? []).map((e) => ({ year: e.year, value: e.value_mt_co2e })),
    })).filter((s) => s.points.length > 0)
  }, [compare, series, sourceSeries])

  const fatal = countries.error ?? indicators.error

  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="brand">
            <img src="/favicon.svg" alt="" />
            Climate Emissions Platform
          </div>
          <nav>
            <a href={`${API_URL}/docs`}>API docs</a>
            <a href={REPO}>GitHub</a>
            <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle dark mode">
              ◐
            </button>
          </nav>
        </div>
      </header>

      <main className="wrap">
        <section className="intro">
          <h1>Greenhouse gas emissions in Europe, 1990 to today</h1>
          <p>
            Official and independent estimates from Eurostat, the World Bank and Our World in Data,
            cleaned and combined into one dataset for 32 European countries.
          </p>
        </section>

        <div className="controls">
          <label>
            Country
            <select value={country} onChange={(e) => setCountry(e.target.value)} disabled={!countries.data}>
              {(countries.data ?? [{ iso2: country, name: countryName }]).map((c) => (
                <option key={c.iso2} value={c.iso2}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
            Compare all three sources
          </label>
        </div>

        {slow && !fatal && (
          <div className="banner" role="status">
            Waking up the API. It runs on a free plan that sleeps when idle, so the first load can
            take up to a minute.
          </div>
        )}
        {fatal && (
          <div className="banner error" role="alert">
            Could not load data: {fatal.message}
          </div>
        )}

        <div className="grid tiles">
          {latest ? (
            <>
              <StatTile
                label={`Total emissions, ${latest.year}`}
                value={formatMt(latest.total_ghg_mt)}
                note={`CO₂e excl. LULUCF · ${SOURCE_LABEL[latest.emissions_source]}`}
              />
              <StatTile
                label="Per person"
                value={latest.ghg_per_capita_t != null ? `${latest.ghg_per_capita_t.toFixed(1)} t` : '–'}
                note="tonnes CO₂e per person"
              />
              <StatTile
                label="Change since 1990"
                value={formatPct(latest.change_vs_1990_pct)}
                delta={null}
                note={latest.change_vs_1990_pct == null ? 'No 1990 value in this source' : 'EU target: −55% by 2030'}
              />
              <StatTile
                label={`Change vs ${latest.year - 1}`}
                value={formatPct(latest.change_vs_prev_year_pct)}
                delta={
                  latest.change_vs_prev_year_pct == null
                    ? null
                    : {
                        text: latest.change_vs_prev_year_pct <= 0 ? 'Falling' : 'Rising',
                        good: latest.change_vs_prev_year_pct <= 0,
                      }
                }
              />
            </>
          ) : (
            [0, 1, 2, 3].map((i) => <div key={i} className="card skeleton" style={{ height: 104 }} />)
          )}
        </div>

        <div className="card section">
          <h2>
            {countryName}: {compare ? 'total emissions by source' : 'total greenhouse gas emissions'}
          </h2>
          <p className="subtitle">
            Mt CO₂e, excluding land use and forestry.{' '}
            {compare
              ? 'Sources differ mainly in method: Eurostat publishes official national inventories; the World Bank and OWID use independent estimates.'
              : `From ${SOURCE_LABEL[latest?.emissions_source ?? 'eurostat']}, the highest-priority source with data for ${countryName}.`}
          </p>
          {indicators.isLoading || (compare && sourceSeries.some((q) => q.isLoading)) ? (
            <div className="skeleton" style={{ height: 300 }} />
          ) : chartSeries.some((s) => s.points.length) ? (
            <TrendChart series={chartSeries} title={`${countryName} greenhouse gas emissions over time`} />
          ) : (
            <p className="empty">No data for this country.</p>
          )}
        </div>

        <div className="grid two section">
          <div className="card">
            <h2>Where the emissions come from{sectorYear ? `, ${sectorYear}` : ''}</h2>
            <p className="subtitle">By sector, Mt CO₂e and share of the total. Source: Eurostat.</p>
            {sectors.isLoading ? (
              <div className="skeleton" style={{ height: 300 }} />
            ) : sectors.data ? (
              <SectorBars sectors={sectors.data.sectors} />
            ) : (
              <p className="empty">
                Sector detail comes from Eurostat, which has no data for {countryName}.
              </p>
            )}
          </div>
          <div className="card">
            <h2>Change since 1990, all countries{latestAll.data ? ` (${latestAll.data.year})` : ''}</h2>
            <p className="subtitle">Click a country to select it.</p>
            {latestAll.data ? (
              <ChangeRanking rows={latestAll.data.countries} selected={country} onSelect={setCountry} />
            ) : (
              <div className="skeleton" style={{ height: 300 }} />
            )}
          </div>
        </div>

        <h2 style={{ fontSize: 18, margin: '32px 0 12px' }}>Data quality</h2>
        {runs.data && reconciliation.data && reconYear ? (
          <QualityPanel
            runs={runs.data}
            reconciliation={reconciliation.data}
            year={reconYear}
            selected={country}
            countryNames={names}
          />
        ) : (
          <div className="skeleton" style={{ height: 220 }} />
        )}
      </main>

      <footer className="wrap">
        <p>
          Data: Eurostat (env_air_gge), World Bank WDI and Our World in Data, all CC BY 4.0. Totals
          exclude LULUCF.
        </p>
        <p>
          Built by <a href="https://smymuna.github.io">Mymuna Sultana</a> · <a href={REPO}>Source code</a>
        </p>
      </footer>
    </>
  )
}
