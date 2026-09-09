import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '../lib/i18n'
import { BlockFrame } from '../components/BlockFrame'

beforeEach(() => {
  document.body.style.overflow = ''
})

describe('BlockFrame — plein écran', () => {
  it('ouvre le rendu en plein écran, verrouille le fond, ferme par Échap et rend le focus', async () => {
    render(
      <BlockFrame typeLabel="diagram" source="```df-diagram\n```">
        <svg data-testid="rendu" />
      </BlockFrame>,
    )

    const trigger = screen.getByTestId('blockframe-fullscreen')
    trigger.focus()
    fireEvent.click(trigger)

    // Overlay ouvert : le rendu est dupliqué dans la vue plein écran, le
    // défilement de fond est verrouillé.
    expect(screen.getByTestId('fullscreen-close')).toBeInTheDocument()
    expect(document.querySelector('.df-fullscreen')).toBeInTheDocument()
    expect(document.body.style.overflow).toBe('hidden')
    expect(screen.getAllByTestId('rendu').length).toBe(2)

    // Échap referme, restaure le défilement et rend le focus au déclencheur.
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('fullscreen-close')).not.toBeInTheDocument())
    expect(document.body.style.overflow).toBe('')
    expect(document.activeElement).toBe(trigger)
  })

  it('ferme par le bouton de fermeture', async () => {
    render(
      <BlockFrame typeLabel="chart" source="x">
        <div data-testid="rendu" />
      </BlockFrame>,
    )
    fireEvent.click(screen.getByTestId('blockframe-fullscreen'))
    fireEvent.click(screen.getByTestId('fullscreen-close'))
    await waitFor(() =>
      expect(screen.queryByTestId('fullscreen-close')).not.toBeInTheDocument(),
    )
  })
})
