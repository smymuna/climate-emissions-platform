import type {
  Country,
  CountryIndicators,
  Emission,
  Page,
  Reconciliation,
  Run,
  SectorBreakdown,
  Source,
  SourceCode,
  YearIndicators,
} from './types'

export const API_URL: string = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
)

/** Error carrying the API's RFC 9457 problem details when there are any. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Params = Record<string, string | number | undefined>

export async function getJson<T>(
  path: string,
  params: Params = {},
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  const url = new URL(API_URL + path)
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) url.searchParams.set(k, String(v))
  }
  let res: Response
  try {
    res = await fetchImpl(url, { headers: { Accept: 'application/json' } })
  } catch {
    throw new ApiError(0, 'Could not reach the API. Check your connection and try again.')
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // not JSON; keep the status line
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const api = {
  countries: () => getJson<Country[]>('/v1/countries'),
  sources: () => getJson<Source[]>('/v1/sources'),
  countryIndicators: (code: string) =>
    getJson<CountryIndicators>(`/v1/countries/${encodeURIComponent(code)}/indicators`),
  yearIndicators: (year?: number) => getJson<YearIndicators>('/v1/indicators', { year }),
  sectors: (code: string, year: number) =>
    getJson<SectorBreakdown>(`/v1/countries/${encodeURIComponent(code)}/sectors`, { year }),
  emissions: (country: string, source: SourceCode) =>
    getJson<Page<Emission>>('/v1/emissions', { country, source, limit: 200 }),
  reconciliation: (year: number) => getJson<Reconciliation[]>('/v1/reconciliation', { year }),
  runs: () => getJson<Run[]>('/v1/runs', { limit: 30 }),
}
