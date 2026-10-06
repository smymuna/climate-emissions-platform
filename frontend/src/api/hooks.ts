import { useQueries, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { SourceCode } from './types'

// Published statistics change a few times a year; there is no need to refetch often.
const STALE = 60 * 60 * 1000

export const SOURCE_ORDER: SourceCode[] = ['eurostat', 'worldbank', 'owid']

export const useCountries = () =>
  useQuery({ queryKey: ['countries'], queryFn: api.countries, staleTime: STALE })

export const useCountryIndicators = (code: string) =>
  useQuery({
    queryKey: ['indicators', code],
    queryFn: () => api.countryIndicators(code),
    staleTime: STALE,
  })

export const useYearIndicators = (year?: number) =>
  useQuery({
    queryKey: ['year-indicators', year ?? 'latest'],
    queryFn: () => api.yearIndicators(year),
    staleTime: STALE,
  })

export const useSectors = (code: string, year: number | undefined) =>
  useQuery({
    queryKey: ['sectors', code, year],
    queryFn: () => api.sectors(code, year as number),
    enabled: year !== undefined,
    staleTime: STALE,
    retry: false, // 404 means "no sector detail for this country/year", not a glitch
  })

/** Total GHG series for one country from every source (for the comparison view). */
export const useSourceSeries = (code: string, enabled: boolean) =>
  useQueries({
    queries: SOURCE_ORDER.map((source) => ({
      queryKey: ['emissions', code, source],
      queryFn: () => api.emissions(code, source),
      enabled,
      staleTime: STALE,
    })),
  })

export const useReconciliation = (year: number | undefined) =>
  useQuery({
    queryKey: ['reconciliation', year],
    queryFn: () => api.reconciliation(year as number),
    enabled: year !== undefined,
    staleTime: STALE,
  })

export const useRuns = () => useQuery({ queryKey: ['runs'], queryFn: api.runs, staleTime: STALE })
