import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ToastProvider, useToast } from '../components/Toast'

function Trigger() {
  const { toast } = useToast()
  return <button onClick={() => toast('Échec HTTP 401 — invalid_workspace_apikey', 'error')}>go</button>
}

describe('Toast', () => {
  it('affiche le message au déclenchement, puis se ferme', () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByText('go'))
    const toast = screen.getByTestId('toast')
    expect(toast).toHaveTextContent('Échec HTTP 401 — invalid_workspace_apikey')

    fireEvent.click(screen.getByLabelText('Fermer'))
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })
})
