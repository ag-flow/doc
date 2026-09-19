/** Canvas générique : rendu, frontière d'abstraction, placement (épic MLD — F6). */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { Canvas } from '../components/canvas/Canvas'
import { autoArrange } from '../lib/canvas/layout'
import { emptyCanvas, type CanvasDoc } from '../lib/canvas/model'

const DOC: CanvasDoc = {
  schemaVersion: 1,
  viewport: { x: 0, y: 0, zoom: 1 },
  nodes: [
    {
      id: 'commande',
      kind: 'table',
      position: { x: 0, y: 0 },
      size: { width: 200, height: 100 },
      ports: [
        { id: 'id', offset: 20, label: 'id' },
        { id: 'client_id', offset: 44, label: 'client_id' },
      ],
      data: { label: 'Commande' },
    },
    {
      id: 'client',
      kind: 'table',
      position: { x: 400, y: 0 },
      size: { width: 200, height: 100 },
      ports: [{ id: 'id', offset: 20, label: 'id' }],
      data: { label: 'Client' },
    },
  ],
  edges: [
    {
      id: 'r1',
      source: { node: 'commande', port: 'client_id' },
      target: { node: 'client', port: 'id' },
      label: 'passée par',
    },
  ],
}

describe('Canvas — rendu', () => {
  it('affiche les nœuds et leurs ports au zoom nominal', () => {
    render(<Canvas doc={DOC} />)

    expect(screen.getByTestId('canvas-node-commande')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-node-client')).toBeInTheDocument()
    expect(screen.getByTestId('canvas-port-commande-client_id')).toBeInTheDocument()
  })

  it('utilise l\'étiquette fournie par l\'appelant', () => {
    // Le canvas est générique : il ne sait pas nommer un nœud, on le lui dit.
    render(<Canvas doc={DOC} labelOf={(n) => `T:${n.id}`} />)
    expect(screen.getByText('T:commande')).toBeInTheDocument()
  })

  it('masque les ports sous le palier de détail', () => {
    const dezoome = { ...DOC, viewport: { x: 0, y: 0, zoom: 0.3 } }
    render(<Canvas doc={dezoome} />)

    expect(screen.getByTestId('canvas')).toHaveAttribute('data-detail', 'silhouette')
    expect(screen.queryByTestId('canvas-port-commande-client_id')).not.toBeInTheDocument()
  })

  it('rend un document vide sans casser', () => {
    render(<Canvas doc={emptyCanvas()} />)
    expect(screen.getByTestId('canvas')).toBeInTheDocument()
  })

  it('n\'appelle pas onChange au simple rendu', () => {
    const onChange = vi.fn()
    render(<Canvas doc={DOC} onChange={onChange} />)
    expect(onChange).not.toHaveBeenCalled()
  })
})

describe('Canvas — frontière d\'abstraction', () => {
  /** Imports réels du module — on ne regarde pas les commentaires, qui ont le
   *  droit de nommer les bibliothèques qu'ils expliquent. */
  const importsOf = (file: string): string[] =>
    [...readFileSync(join(__dirname, '../lib/canvas/', file), 'utf8').matchAll(
      /(?:from|import)\s*\(?\s*['"]([^'"]+)['"]/g,
    )].map((m) => m[1])

  it('l\'API publique n\'importe ni le moteur de rendu ni le placeur', () => {
    // Condition posée par l'étude F1 : le moteur doit rester remplaçable sans
    // toucher aux appelants. Un import qui fuirait ici le rendrait captif.
    expect(importsOf('index.ts').filter((i) => /xyflow|elkjs/.test(i))).toEqual([])
  })

  it.each(['model.ts', 'anchor.ts', 'route.ts', 'detail.ts'])(
    '%s reste pur (ni moteur de rendu, ni placeur)',
    (file) => {
      expect(importsOf(file).filter((i) => /xyflow|elkjs/.test(i))).toEqual([])
    },
  )

  it('elkjs est confiné au seul fichier de placement', () => {
    expect(importsOf('layout.ts').some((i) => i.includes('elkjs'))).toBe(true)
  })
})

describe('autoArrange', () => {
  it('replace tous les nœuds sans les superposer', async () => {
    const colles: CanvasDoc = {
      ...DOC,
      nodes: DOC.nodes.map((n) => ({ ...n, position: { x: 0, y: 0 } })),
    }

    const arrange = await autoArrange(colles)

    const [a, b] = arrange.nodes
    expect(a.position).not.toEqual(b.position)
    expect(arrange.nodes).toHaveLength(2)
  })

  it('ne modifie pas le document d\'entrée', async () => {
    const avant = JSON.stringify(DOC)
    await autoArrange(DOC)
    expect(JSON.stringify(DOC)).toBe(avant)
  })

  it('efface les coudes, devenus faux après déplacement des boîtes', async () => {
    // Les coudes sont en coordonnées absolues : ils n'ont plus de sens une fois
    // les nœuds replacés. Un ré-arrangement est une demande de tout réorganiser.
    const avecCoudes: CanvasDoc = {
      ...DOC,
      edges: [{ ...DOC.edges[0], waypoints: [{ x: 300, y: 300 }] }],
    }

    const arrange = await autoArrange(avecCoudes)
    expect(arrange.edges[0].waypoints).toBeUndefined()
  })

  it('accepte un document vide', async () => {
    const vide = emptyCanvas()
    expect(await autoArrange(vide)).toBe(vide)
  })
})
