import { describe, it, expect, beforeEach } from 'vitest'
import { resolveArtifactUrl } from '../lib/artifacts'

const AID = '550e8400-e29b-41d4-a716-446655440000'
const ARTIFACT_URL = `/api/workspaces/mon-ws/artifacts/${AID}`

describe('resolveArtifactUrl', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('laisse passer les URLs non-artefact inchangées', async () => {
    expect(await resolveArtifactUrl('https://example.com/image.png')).toBe(
      'https://example.com/image.png',
    )
    expect(await resolveArtifactUrl('')).toBe('')
    expect(await resolveArtifactUrl('/api/workspaces/ws/artifacts/pas-un-uuid')).toBe(
      '/api/workspaces/ws/artifacts/pas-un-uuid',
    )
  })

  it("sans token (page publique), route vers l'endpoint public /pub", async () => {
    expect(await resolveArtifactUrl(ARTIFACT_URL)).toBe(`/pub/artifacts/${AID}`)
  })
})
