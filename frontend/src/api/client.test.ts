import { ApiError, getJson } from './client'

const respond = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }),
  )

describe('getJson', () => {
  it('builds the URL with defined params only', async () => {
    const fetchImpl = respond(200, { ok: true })
    await getJson('/v1/indicators', { year: 2022, gas: undefined }, fetchImpl)
    const url = fetchImpl.mock.calls[0][0] as URL
    expect(url.pathname).toBe('/v1/indicators')
    expect(url.searchParams.get('year')).toBe('2022')
    expect(url.searchParams.has('gas')).toBe(false)
  })

  it('surfaces the problem+json detail on errors', async () => {
    const fetchImpl = respond(404, { title: 'Not found', status: 404, detail: "unknown country 'XX'" })
    await expect(getJson('/v1/countries/XX/indicators', {}, fetchImpl)).rejects.toEqual(
      new ApiError(404, "unknown country 'XX'"),
    )
  })

  it('reports network failures in plain words', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(getJson('/healthz', {}, fetchImpl)).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining('Could not reach the API'),
    })
  })
})
