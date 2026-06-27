import { useEffect, useState } from 'react'
import { useMatch, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { api, docsApi, type DataBlockOut, type DocumentOut, type WorkspaceOut } from '../lib/api'

interface Crumb { label: string; href: string | null }

function useDocumentChain(ws: string | null, docId: string | null): DocumentOut[] {
  const [chain, setChain] = useState<DocumentOut[]>([])
  const qc = useQueryClient()

  useEffect(() => {
    if (!ws || !docId) {
      setChain([])
      return
    }
    let cancelled = false
    const visited = new Set<string>()

    async function buildChain(id: string): Promise<DocumentOut[]> {
      if (visited.has(id)) return []
      visited.add(id)
      const doc = await qc.fetchQuery<DocumentOut>({
        queryKey: ['document', ws, id],
        queryFn: () => docsApi.getDocument(ws!, id),
        staleTime: 30_000,
      })
      if (doc.parent_id) {
        const parents = await buildChain(doc.parent_id)
        return [...parents, doc]
      }
      return [doc]
    }

    buildChain(docId)
      .then((c) => { if (!cancelled) setChain(c) })
      .catch(() => { if (!cancelled) setChain([]) })

    return () => { cancelled = true }
  }, [ws, docId, qc])

  return chain
}

export function Breadcrumb() {
  const wsMatch = useMatch('/ws/:wsSlug/*')
  const blocMatch = useMatch('/ws/:wsSlug/blocs/:blocSlug/*')
  const docMatch = useMatch('/ws/:wsSlug/blocs/:blocSlug/documents/:docId')

  const wsSlug = wsMatch?.params.wsSlug ?? null
  const blocSlug = blocMatch?.params.blocSlug ?? null
  const docId = docMatch?.params.docId ?? null

  const { data: workspace } = useQuery<WorkspaceOut>({
    queryKey: ['workspace', wsSlug],
    queryFn: () => api.get<WorkspaceOut>(`/workspaces/${wsSlug}`),
    enabled: Boolean(wsSlug),
  })

  const { data: blocs } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug!),
    enabled: Boolean(wsSlug && blocSlug),
  })

  const bloc = blocs?.find((b) => b.slug === blocSlug) ?? null
  const docChain = useDocumentChain(wsSlug, docId)

  const crumbs: Crumb[] = []
  if (workspace) crumbs.push({ label: workspace.label, href: `/ws/${wsSlug}/blocs` })
  if (bloc) crumbs.push({ label: bloc.label, href: `/ws/${wsSlug}/blocs/${blocSlug}/documents` })
  for (const d of docChain) {
    crumbs.push({
      label: d.title,
      href: `/ws/${wsSlug}/blocs/${blocSlug}/documents/${d.doc_technical_key}`,
    })
  }

  // Le dernier élément n'est pas cliquable (page courante)
  if (crumbs.length > 0) crumbs[crumbs.length - 1].href = null

  if (crumbs.length === 0) return null

  return (
    <div className="flex items-center gap-1 px-6 py-2.5 text-sm border-b border-gray-100 bg-white">
      {crumbs.map((crumb, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight size={13} className="text-gray-300 shrink-0" />}
          {crumb.href ? (
            <Link
              to={crumb.href}
              className="text-gray-400 hover:text-gray-700 transition-colors"
            >
              {crumb.label}
            </Link>
          ) : (
            <span className="font-medium text-gray-800">{crumb.label}</span>
          )}
        </span>
      ))}
    </div>
  )
}
