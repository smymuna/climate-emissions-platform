// Mirrors the response models in src/emissions/api/schemas.py.

export type Gas = 'GHG' | 'CO2'
export type SourceCode = 'eurostat' | 'worldbank' | 'owid'

export interface Country {
  iso2: string
  iso3: string
  name: string
  is_eu27: boolean
}

export interface Source {
  code: SourceCode
  name: string
  url: string
  licence: string
  priority: number
}

export interface Indicator {
  year: number
  total_ghg_mt: number
  emissions_source: SourceCode
  population: number | null
  population_source: SourceCode | null
  ghg_per_capita_t: number | null
  change_vs_1990_pct: number | null
  change_vs_prev_year_pct: number | null
}

export interface CountryIndicators {
  country: Country
  unit: string
  series: Indicator[]
}

export interface CountryYearIndicator extends Indicator {
  country: string
  name: string
}

export interface YearIndicators {
  year: number
  countries: CountryYearIndicator[]
}

export interface Emission {
  country: string
  sector: string
  gas: Gas
  year: number
  value_mt_co2e: number
  source: SourceCode
}

export interface Page<T> {
  data: T[]
  total: number
  limit: number
  offset: number
}

export interface SectorShare {
  sector: string
  name: string
  value_mt_co2e: number
  share_pct: number | null
  source: SourceCode
}

export interface SectorBreakdown {
  country: string
  year: number
  gas: Gas
  total_mt_co2e: number | null
  sectors: SectorShare[]
}

export interface Reconciliation {
  country: string
  gas: Gas
  year: number
  eurostat_mt: number | null
  worldbank_mt: number | null
  owid_mt: number | null
  n_sources: number
  spread_pct: number | null
}

export interface QualityReport {
  steps: { step: string; in: number; out: number }[]
  dropped: Record<string, number>
  rejected: Record<string, number>
  warnings: string[]
  warnings_total: number
}

export interface Run {
  id: number
  source: SourceCode
  status: 'running' | 'succeeded' | 'failed'
  started_at: string
  finished_at: string | null
  records_parsed: number | null
  records_valid: number | null
  records_rejected: number | null
  rows_inserted: number | null
  rows_updated: number | null
  rows_unchanged: number | null
  quality: QualityReport | null
  error: string | null
}
