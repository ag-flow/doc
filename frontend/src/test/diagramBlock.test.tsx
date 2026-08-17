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
        'df-diagram-scatter',
        'df-diagram-gantt',
        'df-diagram-sequence',
        'df-diagram-statemachine',
        'df-diagram-er',
        'df-diagram-loop',
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

  it('pyramid sans valeurs → silhouette géométrique (largeurs de niveau distinctes)', () => {
    const { container } = renderView(' type="pyramid"', 'A\nB\nC')
    const paths = Array.from(container.querySelectorAll('svg[role="img"] path'))
    const topWidths = paths.map((p) => {
      const nums = Array.from((p.getAttribute('d') ?? '').matchAll(/-?\d+(\.\d+)?/g)).map((m) => Number(m[0]))
      return Math.round(nums[2] - nums[0])
    })
    expect(new Set(topWidths).size).toBeGreaterThan(1)
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

  it('quadrant sans xmax/ymax → domaine par défaut, points non empilés', () => {
    const { container } = renderView(' type="quadrant"', 'A | 2 | 3\nB | 8 | 9')
    const circles = Array.from(container.querySelectorAll('svg[role="img"] circle'))
    const positions = circles.map((c) => `${c.getAttribute('cx')},${c.getAttribute('cy')}`)
    expect(new Set(positions).size).toBe(2)
  })

  it('consultant → alias du moteur quadrant', () => {
    const { container } = renderView(' type="consultant"', 'P1 | 5 | 5')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(1)
  })

  it('quadrant — valeur négative → point clampé au bord du domaine, visible dans le viewBox', () => {
    const { container } = renderView(' type="quadrant" xmax="10" ymax="10"', 'Dette | -5 | 3')
    const svg = container.querySelector('svg[role="img"]')!
    const [vbX, vbY, vbW, vbH] = (svg.getAttribute('viewBox') ?? '').split(' ').map(Number)
    const circle = container.querySelector('svg[role="img"] circle')!
    const cx = Number(circle.getAttribute('cx'))
    const cy = Number(circle.getAttribute('cy'))
    expect(cx).toBeGreaterThanOrEqual(vbX)
    expect(cx).toBeLessThanOrEqual(vbX + vbW)
    expect(cy).toBeGreaterThanOrEqual(vbY)
    expect(cy).toBeLessThanOrEqual(vbY + vbH)
  })

  it('radar → 4 anneaux + une série (polygones)', () => {
    const { container } = renderView(' type="radar"', 'A | 5\nB | 8\nC | 3\nD | 6')
    expect(container.querySelectorAll('svg[role="img"] polygon')).toHaveLength(5)
  })

  it('radar — valeur négative → rayon clampé à 0, pas de point reflété de l’autre côté du centre', () => {
    const { container } = renderView(' type="radar"', 'A | -5\nB | 8\nC | 3\nD | 6')
    const polygons = Array.from(container.querySelectorAll('svg[role="img"] polygon'))
    // Le dernier polygone est la série de données (les 4 premiers sont les anneaux).
    const series = polygons[polygons.length - 1]
    const points = (series.getAttribute('points') ?? '')
      .split(' ')
      .filter((p) => p.length > 0)
      .map((p) => p.split(',').map(Number))
    const cx = 320 / 2
    const cy = 300 / 2
    // Le point de l'axe A (valeur -5, rayon clampé à 0) doit coïncider avec le centre.
    const [ax, ay] = points[0]
    expect(Math.hypot(ax - cx, ay - cy)).toBeCloseTo(0, 5)
  })

  it('venn → un cercle par ensemble', () => {
    const { container } = renderView(' type="venn"', 'A | Front\nB | Back\nA&B | Full')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(2)
  })

  it('venn — intersection déclarée avant ses ensembles reste rendue', () => {
    const { getByText, queryByTestId } = renderView(' type="venn"', 'A&B | Fullstack\nA | Frontend\nB | Backend')
    expect(getByText('Fullstack')).toBeInTheDocument()
    expect(queryByTestId('block-diagnostic')).toBeNull()
  })

  it('venn — intersection vers un ensemble inexistant reste ignorée', () => {
    const { getByTestId, queryByText } = renderView(' type="venn"', 'A | Front\nB | Back\nA&Z | Fantome')
    expect(queryByText('Fantome')).toBeNull()
    expect(getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
  })

  it('matrix (dp-security-matrix) → cellules de permission', () => {
    const { container, getByText } = renderView(' type="dp-security-matrix"', ' | Lire | Écrire\nAdmin | ✓ | ✗')
    // 1 ligne × 2 colonnes = 2 cellules.
    expect(container.querySelectorAll('svg[role="img"] rect')).toHaveLength(2)
    expect(getByText('Admin')).toBeInTheDocument()
  })

  it('matrix — cellule "x" affichée en texte brut, pas interprétée comme allow', () => {
    const { getByText, queryByText } = renderView(' type="matrix"', ' | Col\nRow | x')
    expect(getByText('x')).toBeInTheDocument()
    expect(queryByText('✓')).toBeNull()
  })

  it('matrix — "✓" reste allow et "✗" reste deny', () => {
    const { container } = renderView(' type="matrix"', ' | Col\nRow | ✓\nRow2 | ✗')
    const filledCells = container.querySelectorAll('svg[role="img"] rect[fill-opacity]')
    expect(filledCells).toHaveLength(1)
  })

  it('scatter → un point par ligne, axes via Grid', () => {
    const { container } = renderView(' type="scatter"', 'A | 2 | 8\nB | 5 | 5\nC | 8 | 9')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(3)
    expect(container.querySelector('[data-diagram="axis-x"]')).not.toBeNull()
  })

  it('scatter — champ numérique vide → ligne ignorée, pas de point fantôme à 0', () => {
    const { container, getByTestId } = renderView(' type="scatter"', 'A |  | 8\nB | 5 | 5\nC | 8 | 9')
    expect(container.querySelectorAll('svg[role="img"] circle')).toHaveLength(2)
    expect(getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
  })

  it('gantt (dates) → une barre par tâche + axe temporel', () => {
    const { container, getByText } = renderView(
      ' type="gantt"',
      'Cadrage | 2026-01-01 | 2026-01-10\nDév | 2026-01-08 | 2026-02-05',
    )
    // 2 barres (rect) dans le svg du diagramme.
    expect(container.querySelectorAll('svg[role="img"] rect')).toHaveLength(2)
    expect(getByText('Cadrage')).toBeInTheDocument()
  })

  it('sequence → lifelines + messages fléchés', () => {
    const { container, getByText } = renderView(' type="sequence"', 'A -> B | ping\nB -> A | pong')
    expect(container.querySelectorAll('g[data-diagram="message"]')).toHaveLength(2)
    expect(getByText('ping')).toBeInTheDocument()
  })

  it('sequence — 22+ acteurs → boîtes de largeur positive (SVG valide)', () => {
    const actorCount = 24
    const body = Array.from({ length: actorCount - 1 }, (_, i) => `A${i} -> A${i + 1} | m${i}`).join('\n')
    const { container } = renderView(' type="sequence"', body)
    const rects = Array.from(container.querySelectorAll('svg[role="img"] rect'))
    expect(rects.length).toBeGreaterThan(0)
    for (const r of rects) {
      expect(Number(r.getAttribute('width'))).toBeGreaterThan(0)
    }
  })

  it('statemachine → moteur graph avec self-loop', () => {
    const { container } = renderView(' type="statemachine"', 'a -> b | go\nb -> b | tick')
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(2)
    expect(container.querySelector('[data-diagram="self-loop"]')).not.toBeNull()
  })

  it('statemachine → self-loop sur un nœud unique (rangée du haut) reste dans le viewBox', () => {
    const { container } = renderView(' type="statemachine"', 'idle -> idle | tick')
    const svg = container.querySelector('svg[role="img"]')!
    const [, viewBoxY] = (svg.getAttribute('viewBox') ?? '').split(' ').map(Number)

    const path = container.querySelector('[data-diagram="self-loop"] path')!
    const coords = Array.from((path.getAttribute('d') ?? '').matchAll(/-?\d+(\.\d+)?/g)).map((m) => Number(m[0]))
    const ys = coords.filter((_, i) => i % 2 === 1)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(viewBoxY)

    const label = container.querySelector('[data-diagram="self-loop"] text[data-diagram="label"]')!
    expect(Number(label.getAttribute('y'))).toBeGreaterThanOrEqual(viewBoxY)
  })

  it('er → entités multi-champs + relation', () => {
    const { container, getByText } = renderView(' type="er"', 'User\n  id\n  email\nOrder\n  id\nUser -> Order')
    expect(container.querySelectorAll('g[data-diagram="entity"]')).toHaveLength(2)
    expect(getByText('email')).toBeInTheDocument()
  })

  it('er — relation vers une entité non déclarée (typo) → diagnostic avec le bon compte', () => {
    const { getByTestId } = renderView(' type="er"', 'User\n  id\nOrder\n  id\nUser -> Ordre')
    expect(getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
  })

  it('matrix — ligne sans libellé (malformée) → diagnostic avec le bon compte', () => {
    const { getByTestId } = renderView(' type="matrix"', ' | Lire | Écrire\nAdmin | ✓ | ✓\n | ✓ | ✗')
    expect(getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
  })

  it('loop → stations en anneau + hub focal', () => {
    const { container } = renderView(' type="loop" hub="H"', 'A\nB\nC')
    // 3 stations + 1 hub = 4 nœuds.
    expect(container.querySelectorAll('g[data-diagram="node"]')).toHaveLength(4)
    expect(container.querySelector('g[data-variant="focal"]')).not.toBeNull()
  })

  it('loop — ligne malformée (pipe en trop) → diagnostic avec le bon compte', () => {
    const { getByTestId } = renderView(' type="loop"', 'A\nB | extra\nC\nD')
    expect(getByTestId('block-diagnostic')).toHaveTextContent('1 ligne ignorée')
  })

  it('type inconnu → repli + diagnostic, pas de svg', () => {
    const { container, queryByTestId } = renderView(' type="foo"', 'x')
    expect(container.querySelector('svg[role="img"]')).toBeNull()
    expect(container.querySelector('pre')).not.toBeNull()
    expect(queryByTestId('block-diagnostic')).not.toBeNull()
  })
})
