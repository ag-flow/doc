/**
 * Adaptateur modèle de données → canvas (épic MLD — F7).
 *
 * Fait le pont entre deux mondes délibérément séparés :
 *
 * - la **sémantique** — les entités, documents enfants de type `table-schema`,
 *   chacune décrivant ses champs et ses relations ;
 * - la **présentation** — le document contexte `model-layout`, qui dit
 *   seulement où les boîtes sont posées.
 *
 * **Règle qui gouverne tout : l'appartenance au modèle est l'ARBORESCENCE.**
 * La liste des entités vient des documents enfants, jamais du layout. D'où :
 *
 * - une entité **absente du layout** est quand même rendue, à une position
 *   calculée — oublier de la dessiner reviendrait à la faire disparaître d'un
 *   modèle dont elle fait partie ;
 * - une entrée de layout **orpheline** est ignorée — un reliquat de
 *   présentation ne doit pas ressusciter une entité supprimée.
 *
 * Fonctions pures : ni React, ni appel réseau. L'écran se contente de les
 * brancher.
 */

import type { CanvasDoc, CanvasEdge, CanvasNode, CanvasPort, Point } from '../canvas'
import { CANVAS_SCHEMA_VERSION } from '../canvas'

/** Une entité du modèle : un document enfant `table-schema`, déjà parsé. */
export interface Entity {
  /** UUID du document — c'est lui qui identifie l'entité, pas son nom. */
  docId: string
  /** Schéma parsé (grammaire `table-schema`, cf. article 5.8). */
  schema: TableSchema
}

export interface TableSchemaField {
  name?: string
  title?: string
  type?: string
  'docflow.id'?: string
}

export interface TableSchemaRelation {
  name?: string
  title?: string
  cardinality?: string
  from?: string | string[]
  to?: { resource?: string; fields?: string | string[] }
  'docflow.id'?: string
}

export interface TableSchema {
  name?: string
  title?: string
  fields?: TableSchemaField[]
  'docflow.relations'?: TableSchemaRelation[]
}

/** Mise en page — contenu du document `model-layout`, déjà parsé. */
export interface ModelLayout {
  schemaVersion?: number
  viewport?: { x: number; y: number; zoom: number }
  entities?: Array<{
    id: string
    x?: number
    y?: number
    width?: number
    height?: number
    collapsed?: boolean
  }>
  relations?: Array<{ id: string; waypoints?: Point[] }>
}

const HEADER_HEIGHT = 28
const ROW_HEIGHT = 22
const NODE_WIDTH = 220
/** Grille de repli : colonnes larges, pour que rien ne se superpose. */
const AUTO_COLUMN = 320
const AUTO_ROW = 260
const AUTO_PER_ROW = 3

function fieldsOf(schema: TableSchema): TableSchemaField[] {
  return Array.isArray(schema.fields) ? schema.fields : []
}

function relationsOf(schema: TableSchema): TableSchemaRelation[] {
  const rels = schema['docflow.relations']
  return Array.isArray(rels) ? rels : []
}

/** Un port par champ : c'est ce qui permet l'ancrage fin des relations. */
function portsOf(schema: TableSchema): CanvasPort[] {
  return fieldsOf(schema).map((field, i) => ({
    // L'identifiant STABLE prime sur le nom : renommer un champ ne doit pas
    // détacher les liens qui s'y accrochent.
    id: field['docflow.id'] ?? field.name ?? String(i),
    offset: HEADER_HEIGHT + i * ROW_HEIGHT + ROW_HEIGHT / 2,
    label: field.title ?? field.name,
  }))
}

function heightOf(schema: TableSchema): number {
  return HEADER_HEIGHT + Math.max(fieldsOf(schema).length, 1) * ROW_HEIGHT + 8
}

/** Position de repli, en grille, pour une entité absente du layout. */
function autoPosition(index: number): Point {
  return {
    x: (index % AUTO_PER_ROW) * AUTO_COLUMN,
    y: Math.floor(index / AUTO_PER_ROW) * AUTO_ROW,
  }
}

/** Port portant un champ donné, par identifiant stable OU par nom. */
function portIdFor(schema: TableSchema, fieldName: string | undefined): string | undefined {
  if (!fieldName) return undefined
  const field = fieldsOf(schema).find((f) => f.name === fieldName)
  return field?.['docflow.id'] ?? field?.name
}

function firstOf(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

/**
 * Entités + mise en page → document de canvas.
 *
 * `entities` fait foi : c'est la liste des documents enfants. `layout` n'apporte
 * que des positions, et ses entrées orphelines sont ignorées.
 */
export function toCanvas(entities: Entity[], layout: ModelLayout = {}): CanvasDoc {
  const placed = new Map((layout.entities ?? []).map((e) => [e.id, e]))
  const bends = new Map((layout.relations ?? []).map((r) => [r.id, r.waypoints]))

  const nodes: CanvasNode[] = entities.map((entity, index) => {
    const saved = placed.get(entity.docId)
    return {
      id: entity.docId,
      kind: 'entite',
      position:
        saved?.x !== undefined && saved?.y !== undefined
          ? { x: saved.x, y: saved.y }
          : autoPosition(index),
      size: {
        width: saved?.width ?? NODE_WIDTH,
        height: saved?.height ?? heightOf(entity.schema),
      },
      collapsed: saved?.collapsed,
      ports: portsOf(entity.schema),
      data: { label: entity.schema.title ?? entity.schema.name ?? entity.docId },
    }
  })

  // Une relation ne peut être rendue que si sa cible est dans le modèle : elle
  // désigne une table par son NOM, qu'il faut résoudre en document enfant.
  const byName = new Map(
    entities.filter((e) => e.schema.name).map((e) => [e.schema.name as string, e]),
  )

  const edges: CanvasEdge[] = []
  for (const entity of entities) {
    for (const [i, rel] of relationsOf(entity.schema).entries()) {
      const target = byName.get(rel.to?.resource ?? '')
      // Cible hors du modèle (table d'un autre diagramme, ou pas encore créée) :
      // on n'invente pas de nœud fantôme, la relation n'est pas dessinée.
      if (!target) continue

      const id = rel['docflow.id'] ?? `${entity.docId}:${i}`
      edges.push({
        id,
        source: { node: entity.docId, port: portIdFor(entity.schema, firstOf(rel.from)) },
        target: { node: target.docId, port: portIdFor(target.schema, firstOf(rel.to?.fields)) },
        kind: rel.cardinality,
        label: rel.title ?? rel.name,
        waypoints: bends.get(id),
      })
    }
  }

  return {
    schemaVersion: CANVAS_SCHEMA_VERSION,
    viewport: layout.viewport,
    nodes,
    edges,
  }
}

/**
 * Canvas → mise en page à persister.
 *
 * **Ne garde que de la présentation.** Le canvas porte aussi la sémantique
 * (ports, étiquettes) parce qu'il en a besoin pour dessiner ; la réécrire ici
 * la dupliquerait, et deux copies finissent toujours par diverger. La
 * sémantique reste dans les documents enfants, et eux seuls.
 */
export function toLayout(doc: CanvasDoc): ModelLayout {
  const layout: ModelLayout = {
    schemaVersion: 1,
    entities: doc.nodes.map((n) => ({
      id: n.id,
      x: Math.round(n.position.x),
      y: Math.round(n.position.y),
      ...(n.size ? { width: n.size.width, height: n.size.height } : {}),
      ...(n.collapsed ? { collapsed: true } : {}),
    })),
  }
  if (doc.viewport) layout.viewport = doc.viewport

  const bent = doc.edges.filter((e) => e.waypoints?.length)
  if (bent.length) {
    layout.relations = bent.map((e) => ({ id: e.id, waypoints: e.waypoints }))
  }
  return layout
}
