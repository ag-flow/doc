import { describe, it, expect, vi, afterEach } from 'vitest'
import { api, ApiError } from '../lib/api'

function mockFetchOnce(status: number, body: unknown, statusText = '') {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    }),
  )
}

describe('api error message extraction', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('extracts a single message from a FastAPI/Pydantic validation error array', async () => {
    mockFetchOnce(
      422,
      { detail: [{ type: 'value_error', loc: ['body'], msg: 'Value error, auth_secret requis quand auth_storage=local' }] },
      'Unprocessable Entity',
    )
    await expect(api.get('/whatever')).rejects.toMatchObject({
      message: 'auth_secret requis quand auth_storage=local',
    })
  })

  it('joins multiple validation errors', async () => {
    mockFetchOnce(422, {
      detail: [
        { type: 'missing', loc: ['body', 'label'], msg: 'Field required' },
        { type: 'missing', loc: ['body', 'host'], msg: 'Field required' },
      ],
    })
    await expect(api.get('/whatever')).rejects.toMatchObject({
      message: 'Field required ; Field required',
    })
  })

  it('falls back to statusText when detail is not usable', async () => {
    mockFetchOnce(500, {}, 'Internal Server Error')
    await expect(api.get('/whatever')).rejects.toMatchObject({
      message: 'Internal Server Error',
    })
  })

  it('keeps a plain string detail as-is', async () => {
    mockFetchOnce(404, { detail: 'remote point introuvable' })
    await expect(api.get('/whatever')).rejects.toMatchObject({
      message: 'remote point introuvable',
    })
  })

  it('rejects with an ApiError carrying the status code', async () => {
    mockFetchOnce(422, { detail: 'x' })
    try {
      await api.get('/whatever')
      expect.unreachable()
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(422)
    }
  })
})
