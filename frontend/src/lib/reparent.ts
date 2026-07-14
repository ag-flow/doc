import { type AllowedTypeOut, docsApi } from './api'

/** Déplacement d'un document sous un nouveau parent (ou à la racine du bloc).
 *
 *  Règle serveur (DOC-04) : à la racine, le type du document doit être celui
 *  du bloc ; sous un parent, un fils direct du type du parent. Si le type
 *  actuel n'est pas accepté à la destination, il faut le convertir — un seul
 *  candidat = conversion automatique, plusieurs = l'appelant demande à
 *  l'utilisateur (fenêtre de choix).
 */

export interface ReparentPlan {
  /** Types acceptés à la destination. */
  allowed: AllowedTypeOut[]
  /** true si le type actuel est déjà accepté (aucune conversion nécessaire). */
  typeAccepted: boolean
}

export async function planReparent(
  ws: string,
  block: string,
  currentTypeSlug: string | null,
  newParentId: string | null,
): Promise<ReparentPlan> {
  const allowed = await docsApi.getAllowedTypes(ws, block, newParentId ?? undefined)
  return {
    allowed,
    typeAccepted: currentTypeSlug !== null && allowed.some((t) => t.slug === currentTypeSlug),
  }
}

/** Applique le déplacement (et la conversion de type si fournie) — atomique
 *  côté serveur : revalidation de position + purge des valeurs de propriétés
 *  qui n'appartiennent plus au nouveau type. */
export async function applyReparent(
  ws: string,
  docId: string,
  newParentId: string | null,
  typeSlug?: string,
) {
  return docsApi.patchDocument(ws, docId, {
    parent_id: newParentId,
    ...(typeSlug ? { functional_type_slug: typeSlug } : {}),
  })
}
