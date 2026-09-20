/**
 * Cibles possibles d'une relation (épic MLD — F7).
 *
 * Une relation désigne sa cible par le `name` de son schéma — c'est la grammaire
 * Table Schema, et on n'y touche pas. Mais faire SAISIR ce nom à la main était
 * une fabrique à pannes muettes : une faute de frappe ne produit aucune erreur,
 * la relation disparaît simplement du diagramme, l'adaptateur refusant d'inventer
 * une boîte pour une cible qu'il ne résout pas.
 *
 * D'où cette liste : on choisit un DOCUMENT, on écrit son `name`. Le chemin de
 * ses parents l'accompagne, parce que deux modèles d'un même bloc peuvent très
 * bien avoir chacun leur « Client ».
 *
 * Fonctions pures : ni React, ni réseau.
 */

import type { TableSchema } from './adapter'

/** Ce qu'il faut savoir d'un document pour le situer — sous-ensemble de ce que
 *  rend la liste des documents, sans dépendre de sa forme complète. */
export interface DocHead {
  doc_technical_key: string
  title: string
  parent_id: string | null
  data_block_ref: string | null
  functional_type_slug: string | null
  /** Type de CONTENU (`table-schema`, `md`…), pas le type fonctionnel. */
  type: string | null
}

export interface EntityCandidate {
  docId: string
  /** `name` du schéma — c'est LUI qui s'écrit dans `to.resource`. */
  name: string
  /** Titre du document, ce que l'utilisateur lit. */
  title: string
  /** Chemin des parents, du plus haut au plus proche. Vide à la racine. */
  path: string[]
  /** Champs de la cible, pour proposer le champ visé plutôt que le faire saisir. */
  fields: { name: string; title?: string }[]
  /** Appartient au MÊME parent que l'entité courante — donc au même modèle, donc
   *  effectivement dessinable. Une cible d'un autre modèle est un choix légitime
   *  du point de vue des données, mais le diagramme courant ne la tracera pas. */
  sameModel: boolean
}

/** Chemin des titres d'ancêtres, du plus haut au plus proche.
 *
 *  Borné par le nombre de documents : une hiérarchie corrompue en cycle doit
 *  rendre un chemin tronqué, jamais boucler. */
function pathOf(head: DocHead, byId: Map<string, DocHead>): string[] {
  const out: string[] = []
  const seen = new Set<string>([head.doc_technical_key])
  let parent = head.parent_id
  while (parent && !seen.has(parent)) {
    seen.add(parent)
    const node = byId.get(parent)
    if (!node) break
    out.unshift(node.title)
    parent = node.parent_id
  }
  return out
}

function fieldsOf(schema: TableSchema): { name: string; title?: string }[] {
  return (Array.isArray(schema.fields) ? schema.fields : [])
    .filter((f) => f.name)
    .map((f) => ({ name: f.name as string, title: f.title }))
}

/**
 * Cibles proposables depuis l'entité `selfId`.
 *
 * Périmètre : le **bloc** de l'entité courante, et les documents **du même type
 * fonctionnel** — c'est ce qui fait d'un document une entité dans ce workspace,
 * sans qu'aucun slug ne soit codé en dur ici (les types sont définis par
 * l'utilisateur). Le type de contenu doit par ailleurs être `table-schema` :
 * c'est lui qui garantit qu'il y a un `name` et des champs à viser.
 *
 * L'entité courante n'est PAS exclue : une relation réflexive (une catégorie qui
 * a une catégorie parente) est légitime.
 */
export function entityCandidates(
  heads: DocHead[],
  schemas: Map<string, TableSchema>,
  selfId: string,
): EntityCandidate[] {
  const byId = new Map(heads.map((h) => [h.doc_technical_key, h]))
  const self = byId.get(selfId)
  if (!self) return []

  const candidates = heads
    .filter(
      (h) =>
        h.data_block_ref === self.data_block_ref &&
        h.functional_type_slug === self.functional_type_slug &&
        h.type === self.type,
    )
    .map((h) => {
      const schema = schemas.get(h.doc_technical_key)
      return { head: h, name: schema?.name ?? '', fields: fieldsOf(schema ?? {}) }
    })
    // Sans `name`, la cible est indésignable : la proposer mènerait à une
    // relation qui ne résout rien.
    .filter((c) => c.name !== '')
    .map(({ head, name, fields }) => ({
      docId: head.doc_technical_key,
      name,
      title: head.title,
      path: pathOf(head, byId),
      fields,
      sameModel: head.parent_id === self.parent_id,
    }))

  // Le modèle courant d'abord — c'est le cas courant ; le reste par chemin puis
  // par titre, pour que la liste soit stable et lisible.
  return candidates.sort((a, b) => {
    if (a.sameModel !== b.sameModel) return a.sameModel ? -1 : 1
    const byPath = a.path.join('/').localeCompare(b.path.join('/'))
    return byPath !== 0 ? byPath : a.title.localeCompare(b.title)
  })
}
