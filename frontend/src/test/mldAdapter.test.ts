/** Adaptateur modèle de données → canvas (épic MLD — F7). */

import { describe, it, expect } from 'vitest'
import { toCanvas, toLayout, type Entity, type ModelLayout } from '../lib/mld/adapter'

const COMMANDE: Entity = {
  docId: 'doc-commande',
  schema: {
    name: 'commande',
    title: 'Commande',
    fields: [
      { name: 'id', type: 'uuid', 'docflow.id': 'fld_aaaaaaaaaaaa' },
      { name: 'client_id', type: 'uuid', 'docflow.id': 'fld_bbbbbbbbbbbb' },
    ],
    'docflow.relations': [
      {
        name: 'passee_par',
        title: 'Passée par',
        cardinality: 'many-to-one',
        from: 'client_id',
        to: { resource: 'client', fields: 'id' },
        'docflow.id': 'rel_cccccccccccc',
      },
    ],
  },
}

const CLIENT: Entity = {
  docId: 'doc-client',
  schema: {
    name: 'client',
    title: 'Client',
    fields: [{ name: 'id', type: 'uuid', 'docflow.id': 'fld_dddddddddddd' }],
  },
}

// ── Appartenance : l'arborescence fait foi ────────────────────────────────────

describe('toCanvas — l\'appartenance vient de l\'arborescence, pas du layout', () => {
  it('rend une entité absente du layout, à une position calculée', () => {
    // L'oublier reviendrait à la faire disparaître d'un modèle dont elle fait
    // partie : c'est l'arborescence qui décide, pas la mise en page.
    const doc = toCanvas([COMMANDE, CLIENT], { entities: [] })

    expect(doc.nodes.map((n) => n.id)).toEqual(['doc-commande', 'doc-client'])
    expect(doc.nodes[0].position).not.toEqual(doc.nodes[1].position)
  })

  it('ignore une entrée de layout orpheline', () => {
    // Un reliquat de présentation ne doit pas ressusciter une entité supprimée.
    const layout: ModelLayout = {
      entities: [
        { id: 'doc-commande', x: 10, y: 20 },
        { id: 'doc-disparu', x: 999, y: 999 },
      ],
    }
    const doc = toCanvas([COMMANDE], layout)

    expect(doc.nodes).toHaveLength(1)
    expect(doc.nodes[0].id).toBe('doc-commande')
  })

  it('applique les positions enregistrées quand elles existent', () => {
    const doc = toCanvas([COMMANDE], { entities: [{ id: 'doc-commande', x: 42, y: 84 }] })
    expect(doc.nodes[0].position).toEqual({ x: 42, y: 84 })
  })

  it('respecte l\'état replié', () => {
    const doc = toCanvas([COMMANDE], {
      entities: [{ id: 'doc-commande', x: 0, y: 0, collapsed: true }],
    })
    expect(doc.nodes[0].collapsed).toBe(true)
  })
})

// ── Ports et ancrage ──────────────────────────────────────────────────────────

describe('toCanvas — ports', () => {
  it('crée un port par champ, identifié par son identifiant STABLE', () => {
    // Renommer un champ ne doit pas détacher les liens qui s'y accrochent.
    const doc = toCanvas([COMMANDE, CLIENT])
    expect(doc.nodes[0].ports?.map((p) => p.id)).toEqual([
      'fld_aaaaaaaaaaaa',
      'fld_bbbbbbbbbbbb',
    ])
  })

  it('empile les ports verticalement, sans chevauchement', () => {
    const ports = toCanvas([COMMANDE])[ 'nodes' ][0].ports ?? []
    expect(ports[1].offset).toBeGreaterThan(ports[0].offset)
  })

  it('étiquette un port par son titre, sinon son nom', () => {
    const doc = toCanvas([COMMANDE])
    expect(doc.nodes[0].ports?.[0].label).toBe('id')
  })
})

// ── Relations ─────────────────────────────────────────────────────────────────

describe('toCanvas — relations', () => {
  it('relie les deux entités par les ports porteurs', () => {
    const doc = toCanvas([COMMANDE, CLIENT])

    expect(doc.edges).toHaveLength(1)
    expect(doc.edges[0]).toMatchObject({
      id: 'rel_cccccccccccc',
      source: { node: 'doc-commande', port: 'fld_bbbbbbbbbbbb' },
      target: { node: 'doc-client', port: 'fld_dddddddddddd' },
      kind: 'many-to-one',
      label: 'Passée par',
    })
  })

  it('porte la cardinalité, qui dit dans quel sens le lien se lit', () => {
    // Sans elle, un lien ne dit pas si une commande a un client ou l'inverse —
    // c'est l'information la plus utile d'un modèle de données.
    expect(toCanvas([COMMANDE, CLIENT]).edges[0].kind).toBe('many-to-one')
  })

  it('ne dessine pas une relation dont la cible est hors du modèle', () => {
    // On n'invente pas de nœud fantôme pour une table d'un autre diagramme.
    const doc = toCanvas([COMMANDE])
    expect(doc.edges).toEqual([])
  })

  it('reprend les coudes enregistrés pour la relation', () => {
    const layout: ModelLayout = {
      relations: [{ id: 'rel_cccccccccccc', waypoints: [{ x: 300, y: 250 }] }],
    }
    const doc = toCanvas([COMMANDE, CLIENT], layout)
    expect(doc.edges[0].waypoints).toEqual([{ x: 300, y: 250 }])
  })

  it('accepte un modèle vide', () => {
    const doc = toCanvas([])
    expect(doc.nodes).toEqual([])
    expect(doc.edges).toEqual([])
  })
})

// ── Retour vers la mise en page ───────────────────────────────────────────────

describe('toLayout', () => {
  it('ne persiste que de la présentation', () => {
    // La sémantique reste dans les documents enfants : la dupliquer ici la
    // ferait diverger tôt ou tard.
    const layout = toLayout(toCanvas([COMMANDE, CLIENT]))
    const serialise = JSON.stringify(layout)

    expect(serialise).not.toContain('client_id') // nom de champ
    expect(serialise).not.toContain('many-to-one') // cardinalité
    expect(serialise).not.toContain('Passée par') // libellé de relation
  })

  it('conserve positions, tailles et état replié', () => {
    const doc = toCanvas([COMMANDE], {
      entities: [{ id: 'doc-commande', x: 10, y: 20, collapsed: true }],
    })
    const [entity] = toLayout(doc).entities ?? []

    expect(entity).toMatchObject({ id: 'doc-commande', x: 10, y: 20, collapsed: true })
    expect(entity.width).toBeGreaterThan(0)
  })

  it('n\'enregistre que les relations réellement pliées', () => {
    const doc = toCanvas([COMMANDE, CLIENT])
    expect(toLayout(doc).relations).toBeUndefined()

    doc.edges[0].waypoints = [{ x: 1, y: 2 }]
    expect(toLayout(doc).relations).toEqual([
      { id: 'rel_cccccccccccc', waypoints: [{ x: 1, y: 2 }] },
    ])
  })

  it('fait un aller-retour stable', () => {
    const layout: ModelLayout = {
      viewport: { x: 5, y: 6, zoom: 1.5 },
      entities: [
        { id: 'doc-commande', x: 10, y: 20 },
        { id: 'doc-client', x: 300, y: 20 },
      ],
      relations: [{ id: 'rel_cccccccccccc', waypoints: [{ x: 150, y: 90 }] }],
    }
    const reprise = toLayout(toCanvas([COMMANDE, CLIENT], layout))

    expect(reprise.viewport).toEqual(layout.viewport)
    expect(reprise.entities?.map((e) => ({ id: e.id, x: e.x, y: e.y }))).toEqual(layout.entities)
    expect(reprise.relations).toEqual(layout.relations)
  })
})
