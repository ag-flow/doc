import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ReparentDialog } from '../components/ReparentDialog'

vi.mock('../lib/api', () => ({
  docsApi: {
    getAllowedTypes: vi.fn(),
    patchDocument: vi.fn(),
    getBlockDocuments: vi.fn(() => Promise.resolve([])),
  },
}))

import { docsApi } from '../lib/api'

const doc = { id: 'd1', title: 'Doc', type: 'story' }

describe('ReparentDialog (drop imposé)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('déplace sans conversion quand le type est accepté', async () => {
    vi.mocked(docsApi.getAllowedTypes).mockResolvedValue([{ slug: 'story', label: 'Story' }])
    vi.mocked(docsApi.patchDocument).mockResolvedValue({} as never)
    const onDone = vi.fn()
    render(
      <ReparentDialog ws="w" block="b" doc={doc} newParentId="p1" onDone={onDone} onCancel={() => {}} />,
    )
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(docsApi.patchDocument).toHaveBeenCalledWith('w', 'd1', { parent_id: 'p1' })
  })

  it('convertit automatiquement quand un seul type est accepté', async () => {
    vi.mocked(docsApi.getAllowedTypes).mockResolvedValue([{ slug: 'atdd', label: 'ATDD' }])
    vi.mocked(docsApi.patchDocument).mockResolvedValue({} as never)
    const onDone = vi.fn()
    render(
      <ReparentDialog ws="w" block="b" doc={doc} newParentId="p1" onDone={onDone} onCancel={() => {}} />,
    )
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(docsApi.patchDocument).toHaveBeenCalledWith('w', 'd1', {
      parent_id: 'p1',
      functional_type_slug: 'atdd',
    })
  })

  it('demande le type cible quand plusieurs sont acceptés, puis convertit', async () => {
    vi.mocked(docsApi.getAllowedTypes).mockResolvedValue([
      { slug: 'feature', label: 'Feature' },
      { slug: 'bug', label: 'Bug' },
    ])
    vi.mocked(docsApi.patchDocument).mockResolvedValue({} as never)
    const onDone = vi.fn()
    render(
      <ReparentDialog ws="w" block="b" doc={doc} newParentId={null} onDone={onDone} onCancel={() => {}} />,
    )
    // fenêtre de choix affichée, aucun PATCH encore
    await screen.findByTestId('reparent-confirm')
    expect(docsApi.patchDocument).not.toHaveBeenCalled()

    fireEvent.click(screen.getByLabelText(/Bug/))
    fireEvent.click(screen.getByTestId('reparent-confirm'))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(docsApi.patchDocument).toHaveBeenCalledWith('w', 'd1', {
      parent_id: null,
      functional_type_slug: 'bug',
    })
  })
})
