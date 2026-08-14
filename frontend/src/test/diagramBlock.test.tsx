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
      expect.arrayContaining(['df-diagram-layers', 'df-diagram-pyramid', 'df-diagram-nested', 'df-diagram-tree']),
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

  it('type inconnu → repli + diagnostic, pas de svg', () => {
    const { container, queryByTestId } = renderView(' type="foo"', 'x')
    expect(container.querySelector('svg[role="img"]')).toBeNull()
    expect(container.querySelector('pre')).not.toBeNull()
    expect(queryByTestId('block-diagnostic')).not.toBeNull()
  })
})
