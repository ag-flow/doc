import { useEffect, useState } from 'react'
import { useMatch } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { api, docsApi, type DataBlockOut, type DocumentOut, type WorkspaceOut } from '../lib/api'

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

  const crumbs: string[] = []
  if (workspace) crumbs.push(workspace.label)
  if (bloc) crumbs.push(bloc.label)
  for (const d of docChain) crumbs.push(d.title)

  if (crumbs.length === 0) return null

  return (
    <div className="flex items-center gap-1 px-6 py-2.5 text-sm border-b border-gray-100 bg-white">
      {crumbs.map((crumb, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight size={13} className="text-gray-300 shrink-0" />}
          <span className={i === crumbs.length - 1 ? 'font-medium text-gray-800' : 'text-gray-400'}>
            {crumb}
          </span>
        </span>
      ))}
    </div>
  )
}
