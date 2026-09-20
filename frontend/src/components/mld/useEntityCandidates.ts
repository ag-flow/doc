/**
 * Chargement des cibles de relation possibles (épic MLD — F7).
 *
 * Isolé du rendu : la grille de relations reçoit une LISTE, elle n'interroge
 * rien. C'est ce qui la garde testable sans réseau, et ce qui permet d'échanger
 * la source des candidats sans y toucher.
 */

import { useMemo } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { parse as parseYaml } from 'yaml'
import { docsApi, type DocumentOut } from '../../lib/api'
import { useWorkspaceSlugOrNull } from '../../contexts/WorkspaceContext'
import { entityCandidates, type EntityCandidate } from '../../lib/mld/candidates'
import type { TableSchema } from '../../lib/mld/adapter'

function safeParse(raw: string | null | undefined): TableSchema {
  if (!raw?.trim()) return {}
  try {
    return (parseYaml(raw) as TableSchema) ?? {}
  } catch {
    return {}
  }
}

/**
 * Entités désignables depuis le document `docId`.
 *
 * `listDocuments` ne rend que des TÊTES (`content` toujours null) : elle situe
 * les documents dans l'arbre, mais le `name` du schéma — celui qu'on écrit dans
 * la relation — est dans le CORPS. D'où le second temps, un corps par candidat.
 *
 * Même compromis que la surface de modèle : acceptable à l'échelle d'un bloc de
 * modèles, à remplacer par un point d'entrée qui rend les corps en une fois si
 * les blocs grossissent.
 */
export function useEntityCandidates(docId: string | undefined): EntityCandidate[] {
  const wsSlug = useWorkspaceSlugOrNull()

  const { data: heads } = useQuery<DocumentOut[]>({
    queryKey: ['mld-candidate-heads', wsSlug],
    queryFn: () => docsApi.listDocuments(wsSlug as string),
    enabled: Boolean(wsSlug && docId),
    staleTime: 30_000,
  })

  // Pré-filtrage sur les seules têtes : inutile de charger le corps d'un
  // document qui n'est de toute façon pas une entité de ce bloc.
  const peerIds = useMemo(() => {
    const self = (heads ?? []).find((d) => d.doc_technical_key === docId)
    if (!self) return []
    return (heads ?? [])
      .filter(
        (d) =>
          d.data_block_ref === self.data_block_ref &&
          d.functional_type_slug === self.functional_type_slug &&
          d.type === self.type,
      )
      .map((d) => d.doc_technical_key)
  }, [heads, docId])

  const bodies = useQueries({
    queries: peerIds.map((id) => ({
      queryKey: ['document', wsSlug, id],
      queryFn: () => docsApi.getDocument(wsSlug as string, id),
      staleTime: 30_000,
    })),
  })

  const schemas = useMemo(() => {
    const map = new Map<string, TableSchema>()
    for (const q of bodies) {
      if (q.data) map.set(q.data.doc_technical_key, safeParse(q.data.content))
    }
    return map
  }, [bodies])

  return useMemo(
    () => (heads && docId ? entityCandidates(heads, schemas, docId) : []),
    [heads, schemas, docId],
  )
}
