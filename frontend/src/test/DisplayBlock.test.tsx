import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '../lib/i18n'
import { DisplayView } from '../components/DisplayBlock'
import { ICON_NAMES } from '../components/displayCatalog'

const ADR_BODY = JSON.stringify([
  { id: 'root', component: 'Column', children: ['title', 'cards', 'bar'] },
  { id: 'title', component: 'Text', text: 'Comparatif', hint: 'h2' },
  { id: 'cards', component: 'Row', children: ['c1', 'c2'] },
  { id: 'c1', component: 'Card', children: ['c1t', 'c1b'] },
  { id: 'c1t', component: 'Text', text: 'Option A', hint: 'h3' },
  { id: 'c1b', component: 'Badge', text: 'Recommandé', variant: 'accent' },
  { id: 'c2', component: 'Card', children: ['c2t'] },
  { id: 'c2t', component: 'Chip', text: 'Option B', variant: 'alert' },
  { id: 'bar', component: 'ProgressBar', value: 130, label: 'Avancement' },
])

describe('DisplayView', () => {
  it('rend l’exemple ADR : textes, badge cyan, chip magenta, progress bornée', () => {
    render(<DisplayView attrs=' title="Démo"' body={ADR_BODY} source="s" />)
    expect(screen.getByText('Comparatif')).toBeInTheDocument()
    expect(screen.getByText('Option A')).toBeInTheDocument()
    expect(screen.getByText('Recommandé').className).toContain('tag-accent')
    expect(screen.getByText('Option B').className).toContain('tag-accent-2')
    // value 130 → bornée à 100.
    expect(screen.getByTestId('display-progress')).toHaveStyle({ width: '100%' })
    // Aucun diagnostic sur un bloc valide.
    expect(screen.queryByTestId('block-diagnostic')).not.toBeInTheDocument()
  })

  it('composant inconnu → texte grisé + badge, les enfants rendent', () => {
    render(<DisplayView attrs="" source="s" body={JSON.stringify([
      { id: 'root', component: 'Wormhole', children: ['in'] },
      { id: 'in', component: 'Text', text: 'survivant' },
    ])} />)
    expect(screen.getByTestId('display-unknown-root')).toHaveTextContent('composant inconnu : Wormhole')
    expect(screen.getByText('survivant')).toBeInTheDocument()
    expect(screen.getByText('1 composant inconnu')).toBeInTheDocument()
  })

  it('variant hors vocabulaire → neutral ; icône inconnue → cercle grisé', () => {
    render(<DisplayView attrs="" source="s" body={JSON.stringify([
      { id: 'root', component: 'Row', children: ['b', 'i'] },
      { id: 'b', component: 'Badge', text: 'X', variant: 'success' },
      { id: 'i', component: 'Icon', name: 'licorne' },
    ])} />)
    expect(screen.getByText('X').className).toContain('tag-neutral')
    expect(screen.getByTestId('display-icon-unknown')).toBeInTheDocument()
  })

  it('image non autorisée (http:) → placeholder, jamais de <img>', () => {
    const { container } = render(<DisplayView attrs="" source="s" body={JSON.stringify([
      { id: 'root', component: 'Image', src: 'http://tracker.example/pix.png', alt: 'x' },
    ])} />)
    expect(screen.getByTestId('display-image-blocked')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('orphelins et références mortes → badges, rendu partiel conservé', () => {
    render(<DisplayView attrs="" source="s" body={JSON.stringify([
      { id: 'root', component: 'Row', children: ['ok', 'fantome'] },
      { id: 'ok', component: 'Text', text: 'là' },
      { id: 'seul', component: 'Text', text: 'orphelin' },
    ])} />)
    expect(screen.getByText('là')).toBeInTheDocument()
    expect(screen.getByText('1 composant non rattaché')).toBeInTheDocument()
    expect(screen.getByText('1 référence morte')).toBeInTheDocument()
  })

  it('JSON illisible → source affichée en dégradation, aucun crash', () => {
    render(<DisplayView attrs="" source="s" body="{pas du json" />)
    expect(screen.getByText('{pas du json')).toBeInTheDocument()
  })

  it('le catalogue d’icônes publié compte bien ~30 noms stables', () => {
    expect(ICON_NAMES.length).toBe(30)
    expect(ICON_NAMES).toContain('check')
    expect(ICON_NAMES).toContain('trend-up')
  })
})
