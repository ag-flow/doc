import { describe, it, expect, vi, afterEach } from 'vitest'
import { drainSseBuffer, watchDocument } from '../lib/docWatch'

describe('drainSseBuffer', () => {
  it('découpe les messages complets, ignore les commentaires, garde le reste', () => {
    const emitted: Array<[string | null, string | null]> = []
    const rest = drainSseBuffer(
      'event: change\ndata: {"v":1}\n\n: keepalive\n\nevent: change\ndata: {"v"',
      (e, d) => emitted.push([e, d]),
    )
    expect(emitted).toEqual([['change', '{"v":1}']])
    expect(rest).toBe('event: change\ndata: {"v"')
  })
})

describe('watchDocument', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('émet change puis s’arrête net sur gone (aucune reconnexion)', async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const enc = new TextEncoder()
        controller.enqueue(enc.encode(
          'event: change\ndata: {"document_id":"d1","version":2,"updated_at":"t","updated_by":"agent"}\n\n',
        ))
        controller.enqueue(enc.encode('event: gone\ndata: {"document_id":"d1"}\n\n'))
        controller.close()
      },
    })
    const fetchMock = vi.fn(async () => new Response(body, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const onChange = vi.fn()
    const onGone = vi.fn()
    const stop = watchDocument('ws', 'd1', { onChange, onGone })
    await vi.waitFor(() => expect(onGone).toHaveBeenCalled())
    expect(onChange).toHaveBeenCalledWith({
      document_id: 'd1', version: 2, updated_at: 't', updated_by: 'agent',
    })
    // gone = terminal : pas de tentative de reconnexion.
    await new Promise((r) => setTimeout(r, 30))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    stop()
  })
})
