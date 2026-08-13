import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Node, Edge, Label, Grid, Annotation } from '../components/diagram'
import { cartesianFrame } from '../lib/diagramLayout'

/** Rend des primitives dans un <svg> (contexte requis) et renvoie le conteneur. */
function renderSvg(node: React.ReactNode) {
  return render(<svg>{node}</svg>)
}

describe('Label', () => {
  it('positionne le texte et applique la police de la variante', () => {
    const { container } = renderSvg(
      <Label x={10} y={20} variant="node" anchor="middle">
        Alice
      </Label>,
    )
    const t = container.querySelector('text')!
    expect(t.getAttribute('x')).toBe('10')
    expect(t.getAttribute('y')).toBe('20')
    expect(t.getAttribute('text-anchor')).toBe('middle')
    expect(t.getAttribute('font-family')).toBe('var(--diagram-font-node)')
    expect(t.getAttribute('fill')).toBe('var(--diagram-ink)')
    expect(t.textContent).toBe('Alice')
  })

  it('variante muted → mono + teinte muted', () => {
    const { container } = renderSvg(<Label x={0} y={0} variant="muted">42</Label>)
    const t = container.querySelector('text')!
    expect(t.getAttribute('font-family')).toBe('var(--diagram-font-mono)')
    expect(t.getAttribute('fill')).toBe('var(--diagram-muted)')
  })
})

describe('Node', () => {
  const rect = { x: 10, y: 20, width: 100, height: 40 }

  it('rend un rect aux dimensions du Rect, bordure hairline par défaut', () => {
    const { container } = renderSvg(<Node rect={rect} label="Service" />)
    const r = container.querySelector('rect')!
    expect(r.getAttribute('x')).toBe('10')
    expect(r.getAttribute('width')).toBe('100')
    expect(r.getAttribute('height')).toBe('40')
    expect(r.getAttribute('fill')).toBe('var(--diagram-paper-2)')
    expect(r.getAttribute('stroke')).toBe('var(--diagram-hairline-color)')
    expect(container.querySelector('text')!.textContent).toBe('Service')
  })

  it('variante focal → bordure accent', () => {
    const { container } = renderSvg(<Node rect={rect} label="Focus" variant="focal" />)
    expect(container.querySelector('rect')!.getAttribute('stroke')).toBe('var(--diagram-accent)')
    expect(container.querySelector('g[data-diagram="node"]')!.getAttribute('data-variant')).toBe('focal')
  })

  it('centre le label et pose le sublabel sous lui', () => {
    const { container } = renderSvg(<Node rect={rect} label="Titre" sublabel="v2" />)
    const texts = container.querySelectorAll('text')
    expect(texts).toHaveLength(2)
    // Centre horizontal = x + width/2 = 60
    expect(texts[0].getAttribute('x')).toBe('60')
    expect(texts[1].getAttribute('x')).toBe('60')
    expect(texts[1].getAttribute('fill')).toBe('var(--diagram-muted)')
  })
})

describe('Edge', () => {
  it('trait droit entre deux points, sans flèche par défaut', () => {
    const { container } = renderSvg(<Edge from={{ x: 0, y: 0 }} to={{ x: 100, y: 50 }} />)
    const path = container.querySelector('path[data-diagram]')
    expect(container.querySelector('path')!.getAttribute('d')).toBe('M0 0 L100 50')
    expect(container.querySelector('[data-diagram="arrow"]')).toBeNull()
    expect(path).toBeNull() // le path principal n'a pas data-diagram; l'arrow oui
  })

  it('variante orthogonale → coude médian', () => {
    const { container } = renderSvg(<Edge from={{ x: 0, y: 0 }} to={{ x: 100, y: 40 }} variant="orthogonal" />)
    expect(container.querySelector('path')!.getAttribute('d')).toBe('M0 0 L50 0 L50 40 L100 40')
  })

  it('flèche → un second path triangulaire à l’extrémité', () => {
    const { container } = renderSvg(<Edge from={{ x: 0, y: 0 }} to={{ x: 100, y: 0 }} arrow />)
    const arrow = container.querySelector('[data-diagram="arrow"]')!
    expect(arrow).not.toBeNull()
    expect(arrow.getAttribute('fill')).toBe('var(--diagram-ink)')
    expect(arrow.getAttribute('d')!.startsWith('M100 0')).toBe(true)
  })

  it('pointillés et focal accent', () => {
    const { container } = renderSvg(<Edge from={{ x: 0, y: 0 }} to={{ x: 10, y: 10 }} dashed focal />)
    const p = container.querySelector('path')!
    expect(p.getAttribute('stroke-dasharray')).toBe('4 3')
    expect(p.getAttribute('stroke')).toBe('var(--diagram-accent)')
  })
})

describe('Grid', () => {
  it('trace axes + lignes de repère aux graduations du frame', () => {
    const frame = cartesianFrame({ width: 100, height: 100, padding: 0, xDomain: [0, 4], yDomain: [0, 4] })
    const { container } = renderSvg(<Grid frame={frame} />)
    expect(container.querySelector('[data-diagram="axis-x"]')).not.toBeNull()
    expect(container.querySelector('[data-diagram="axis-y"]')).not.toBeNull()
    // Graduations rondes 0..4 (pas 1) → 5 lignes verticales + 5 horizontales.
    expect(container.querySelectorAll('[data-diagram="gridline"]').length).toBe(10)
  })

  it('libellés optionnels en mono/muted', () => {
    const frame = cartesianFrame({ width: 100, height: 100, padding: 10, xDomain: [0, 2], yDomain: [0, 2] })
    const { container } = renderSvg(<Grid frame={frame} labels vertical={false} horizontal={false} axes={false} />)
    const texts = container.querySelectorAll('text')
    expect(texts.length).toBeGreaterThan(0)
    expect(texts[0].getAttribute('fill')).toBe('var(--diagram-muted)')
  })
})

describe('Annotation', () => {
  it('texte sérif italique en teinte muted', () => {
    const { container } = renderSvg(<Annotation x={5} y={5}>note</Annotation>)
    const t = container.querySelector('text')!
    expect(t.getAttribute('font-family')).toBe('var(--diagram-font-title)')
    expect(t.getAttribute('font-style')).toBe('italic')
    expect(t.getAttribute('fill')).toBe('var(--diagram-muted)')
  })

  it('ligne de rappel vers le point cible', () => {
    const { container } = renderSvg(<Annotation x={5} y={5} to={{ x: 40, y: 30 }}>vers</Annotation>)
    const leader = container.querySelector('[data-diagram="leader"]')!
    expect(leader.getAttribute('x1')).toBe('5')
    expect(leader.getAttribute('x2')).toBe('40')
    expect(leader.getAttribute('y2')).toBe('30')
  })
})
