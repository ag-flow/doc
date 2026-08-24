import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import {
  Icon,
  ICON_NAMES,
  SketchyDefs,
  sketchy,
  SKETCHY_FILTER_ID,
  TerminalFrame,
  Annotation,
} from '../components/diagram'

function renderSvg(node: React.ReactNode) {
  return render(<svg>{node}</svg>)
}

describe('Icon', () => {
  it('rend un glyphe en currentColor, positionnable', () => {
    const { container } = renderSvg(<Icon name="server" x={10} y={20} size={16} />)
    const svg = container.querySelector('svg[data-diagram="icon"]')!
    expect(svg.getAttribute('stroke')).toBe('currentColor')
    expect(svg.getAttribute('fill')).toBe('none')
    expect(svg.getAttribute('x')).toBe('10')
    expect(svg.getAttribute('width')).toBe('16')
    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24')
    expect(svg.getAttribute('data-icon')).toBe('server')
    expect(svg.getAttribute('aria-label')).toBe('server')
  })

  it('expose le catalogue complet (≥ 55 icônes), toutes rendables', () => {
    // 55 est la cible de l'enabler « Primitives transverses ». Seuil et non
    // égalité : ajouter une icône ne doit pas casser le test, en retirer sous
    // la cible doit le casser.
    expect(ICON_NAMES.length).toBeGreaterThanOrEqual(55)
    expect(new Set(ICON_NAMES).size).toBe(ICON_NAMES.length) // pas de doublon
    for (const name of ICON_NAMES) {
      const { container } = renderSvg(<Icon name={name} />)
      // Chaque glyphe produit au moins un élément géométrique.
      expect(container.querySelector('svg[data-diagram="icon"]')!.childElementCount).toBeGreaterThan(0)
    }
  })

  it('couvre les briques IT/cloud nommées par l’enabler', () => {
    // Ce que la fiche cite explicitement : sans elles, le catalogue est hors sujet
    // quel que soit son volume.
    for (const name of ['laptop', 'server', 'database', 'docker', 'kubernetes', 'aws', 'azure', 'github', 'postgres']) {
      expect(ICON_NAMES).toContain(name)
    }
  })

  it('ne pose fill=currentColor que sur des aplats, jamais sur un tracé ouvert', () => {
    // Un <path> de contour rempli produit une tache noire au rendu : le style de
    // trait est porté par <Icon> (fill:none), les glyphes ne remplissent que les
    // pastilles/points.
    for (const name of ICON_NAMES) {
      const { container } = renderSvg(<Icon name={name} />)
      for (const el of container.querySelectorAll('[fill="currentColor"]')) {
        expect(['circle', 'text'], `${name}: <${el.tagName}> rempli`).toContain(el.tagName.toLowerCase())
      }
    }
  })
})

describe('SketchyDefs / sketchy', () => {
  it('déclare un filtre turbulence + déplacement', () => {
    const { container } = renderSvg(<SketchyDefs />)
    const filter = container.querySelector(`filter#${SKETCHY_FILTER_ID}`)!
    expect(filter).not.toBeNull()
    expect(filter.querySelector('feTurbulence')).not.toBeNull()
    expect(filter.querySelector('feDisplacementMap')).not.toBeNull()
  })

  it('sketchy() renvoie la référence url(#id)', () => {
    expect(sketchy()).toBe(`url(#${SKETCHY_FILTER_ID})`)
    expect(sketchy('x')).toBe('url(#x)')
  })
})

describe('TerminalFrame', () => {
  const rect = { x: 0, y: 0, width: 200, height: 120 }

  it('fond charcoal + trois pastilles + titre mono clair', () => {
    const { container } = renderSvg(<TerminalFrame rect={rect} title="bash" />)
    const bg = container.querySelector('g[data-diagram="terminal"] > rect')!
    expect(bg.getAttribute('fill')).toBe('var(--diagram-terminal-bg)')
    expect(container.querySelectorAll('[data-diagram="terminal-dot"]')).toHaveLength(3)
    const title = container.querySelector('text')!
    expect(title.getAttribute('fill')).toBe('var(--diagram-terminal-fg)')
    expect(title.getAttribute('font-family')).toBe('var(--diagram-font-mono)')
  })

  it('translate la zone de contenu sous la barre', () => {
    const { container } = renderSvg(
      <TerminalFrame rect={rect}>
        <circle cx="0" cy="0" r="1" />
      </TerminalFrame>,
    )
    const content = container.querySelector('[data-diagram="terminal-content"]')!
    expect(content.getAttribute('transform')).toBe('translate(10 28)')
  })
})

describe('Annotation — leader Bézier (variante transverse)', () => {
  it('leader droit par défaut (rétro-compat)', () => {
    const { container } = renderSvg(<Annotation x={0} y={0} to={{ x: 10, y: 10 }}>n</Annotation>)
    expect(container.querySelector('line[data-diagram="leader"]')).not.toBeNull()
  })

  it('curved → path Bézier quadratique pointillé', () => {
    const { container } = renderSvg(<Annotation x={0} y={0} to={{ x: 40, y: 0 }} curved>n</Annotation>)
    const leader = container.querySelector('path[data-diagram="leader"]')!
    expect(leader).not.toBeNull()
    expect(leader.getAttribute('d')!.includes('Q')).toBe(true)
    expect(leader.getAttribute('stroke-dasharray')).toBe('3 3')
  })
})
