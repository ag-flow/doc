import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import '../lib/i18n'
import { diagramCodec } from '../lib/blockCodecs/diagram'
import { slashItemsFromRegistry, type SlashContext } from '../lib/blockCodecs'
import { DiagramView } from '../components/DiagramBlock'

describe('diagramCodec — round-trip markdown', () => {
  it('toBlock puis toMarkdown est stable', () => {
    const md = '```df-diagram type="tree"\nRacine\n  Enfant\n```'
    const re = new RegExp(diagramCodec.pattern.source, diagramCodec.pattern.flags)
    const match = re.exec(md)!
    const props = diagramCodec.toBlock(match)
    expect(props).toEqual({ attrs: ' type="tree"', body: 'Racine\n  Enfant' })
    expect(diagramCodec.toMarkdown(props)).toBe(md)
  })
})

describe('menu slash — un item par type', () => {
  it('expose layers/pyramid/nested/tree via le registre', () => {
    const ctx: SlashContext = {
      editor: { insertBlocks: () => {}, getTextCursorPosition: () => ({ block: null }) },
      wsSlug: 'w',
      t: (k: string) => k,
    }
    const keys = slashItemsFromRegistry(ctx).map((i) => i.key)
    expect(keys).toEqual(
      expect.arrayContaining([
        'df-diagram-layers',
        'df-diagram-pyramid',
        'df-diagram-nested',
        'df-diagram-tree',
        'df-diagram-graph',
        'df-diagram-swimlane',
        'df-diagram-org',
        'df-diagram-quadrant',
        'df-diagram-radar',
        'df-diagram-venn',
        'df-diagram-matrix',
      ]),
    )
  })
})

function renderView(attrs: string, body: string) {
  return render(<DiagramView attrs={attrs} body={body} source="s" />)
}

describe('DiagramView — dispatch par type', () => {
  it('layers → une boîte par ligne', () => {
    const { container } = renderView(' type="layers"', 'A | x\nB | y\nC')
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(3)
  })

  it('pyramid → un trapèze (path) par niveau', () => {
    const { container } = renderView(' type="pyramid"', 'Haut\nBas')
    // Scoper sur le svg du diagramme (role=img) : BlockFrame rend aussi des icônes.
    expect(container.querySelectorAll('svg[role="img"] path')).toHaveLength(2)
  })

  it('nested → boîtes imbriquées', () => {
    const { container } = renderView(' type="nested"', 'Système\n  Module\n    Fonction')
    expect(container.querySelectorAll('g[data-diagram="nested-node"]').length).toBe(3)
  })

  it('tree → nœuds + arêtes orthogonales', () => {
    const { container } = renderView(' type="tree"', 'Racine\n  C1\n  C2')
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(3)
    expect(container.querySelectorAll('g[data-diagram="edge"]')).toHaveLength(2)
  })

  it('graph → nœuds + arêtes fléchées', () => {
    const { container } = renderView(' type="graph"', 'A | Alpha\nB | Beta\nA -> B')
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(2)
    expect(container.querySelectorAll('g[data-diagram="edge"]')).toHaveLength(1)
    expect(container.querySelector('[data-diagram="arrow"]')).not.toBeNull()
  })

  it('alias sémantique medallion → moteur graph', () => {
    const { container } = renderView(' type="medallion"', 'r | Raw | Bronze\nc | Clean | Silver\nr -> c')
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(2)
  })

  it('swimlane → couloirs + étapes', () => {
    const { container } = renderView(' type="swimlane"', 'Vente | Devis\nVente | Validation\nLivraison | Envoi')
    expect(container.querySelectorAll('g[data-diagram="lane"]')).toHaveLength(2)
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(3)
  })

  it('org → réutilise le moteur tree (nœuds + arêtes)', () => {
    const { container } = renderView(' type="org"', 'Dir\n  A\n  B')
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(3)
    expect(container.querySelectorAll('g[data-diagram="edge"]')).toHaveLength(2)
  })

  it('quadrant → un point par item + cellules nommées', () => {
    const { container } = renderView(' type="quadrant" quadrants="A,B,C,D"', 'X | 8 | 9\nY | 2 | 3')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(2)
  })

  it('consultant → alias du moteur quadrant', () => {
    const { container } = renderView(' type="consultant"', 'P1 | 5 | 5')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(1)
  })

  it('radar → 4 anneaux + une série (polygones)', () => {
    const { container } = renderView(' type="radar"', 'A | 5\nB | 8\nC | 3\nD | 6')
    expect(container.querySelectorAll('svg[role="img"] polygon')).toHaveLength(5)
  })

  it('venn → un cercle par ensemble', () => {
    const { container } = renderView(' type="venn"', 'A | Front\nB | Back\nA&B | Full')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(2)
  })

  it('matrix (dp-security-matrix) → cellules de permission', () => {
    const { container, getByText } = renderView(' type="dp-security-matrix"', ' | Lire | Écrire\nAdmin | ✓ | ✗')
    // 1 ligne × 2 colonnes = 2 cellules.
    expect(container.querySelectorAll('svg[role="img"] rect')).toHaveLength(2)
    expect(getByText('Admin')).toBeInTheDocument()
  })

  it('type inconnu → repli + diagnostic, pas de svg', () => {
    const { container, queryByTestId } = renderView(' type="foo"', 'x')
    expect(container.querySelector('svg[role="img"]')).toBeNull()
    expect(container.querySelector('pre')).not.toBeNull()
    expect(queryByTestId('block-diagnostic')).not.toBeNull()
  })
})
