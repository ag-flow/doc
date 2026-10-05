import { useEffect, useState } from 'react'
import { useMatch, useLocation, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { truncateMiddle } from '../lib/truncateMiddle'
import { api, docsApi, type DataBlockOut, type DocumentOut, type WorkspaceOut } from '../lib/api'

interface Crumb { label: string; href: string | null }

/** Écrans hors workspace : leur fil d'Ariane est le nom de l'écran. Il remplace
 *  le titre de page — d'où une entrée par route, sans titre redondant ailleurs. */
const STATIC_LABELS: Record<string, string> = {
  '/workspaces': 'Workspaces',
  '/templates': 'Templates',
  '/contracts': 'Contrats OpenAPI',
  '/api-keys': 'Clés API',
  '/me': 'Mon profil',
  '/admin/users': 'Utilisateurs',
  '/admin/vault': 'Wallets Vault',
  '/admin/oidc': 'Config OIDC',
  '/admin/events-producer': 'Connexion workflow',
  '/admin/remote': 'Connexions & Sauvegarde',
}

/** Sections d'un workspace : dernier segment de l'URL → libellé affiché. */
const WS_SECTIONS: Record<string, string> = {
  types: 'Types fonctionnels',
  blocs: 'Blocs',
  webhooks: 'Webhooks',
  automations: 'Automates',
}

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

/** Fil d'Ariane `workspace / bloc / document`. Chaque segment est cliquable,
 *  le dernier est la page courante. */
export function Breadcrumb() {
  const { pathname } = useLocation()
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
  if (wsSlug) {
    crumbs.push({ label: workspace?.label ?? wsSlug, href: `/ws/${wsSlug}/blocs` })
    if (bloc) {
      crumbs.push({ label: bloc.label, href: `/ws/${wsSlug}/blocs/${blocSlug}/documents` })
    } else {
      const section = WS_SECTIONS[pathname.split('/')[3] ?? '']
      if (section) crumbs.push({ label: section, href: null })
    }
    for (const d of docChain) {
      crumbs.push({
        label: d.title,
        href: `/ws/${wsSlug}/blocs/${blocSlug}/documents/${d.doc_technical_key}`,
      })
    }
  } else {
    const label = STATIC_LABELS[pathname]
    if (label) crumbs.push({ label, href: null })
  }

  // Le dernier segment est la page courante : jamais cliquable.
  if (crumbs.length > 0) crumbs[crumbs.length - 1].href = null

  if (crumbs.length === 0) return null

  return (
    <span className="crumbs" data-testid="breadcrumb">
      {crumbs.map((crumb, i) => (
        <span key={i} className="crumbs">
          {crumb.href ? (
            <Link to={crumb.href} className="crumb" title={crumb.label}>
              {truncateMiddle(crumb.label)}
            </Link>
          ) : (
            <span className="crumb crumb-current" title={crumb.label}>
              {truncateMiddle(crumb.label)}
            </span>
          )}
          {i < crumbs.length - 1 && <span className="crumb-sep">/</span>}
        </span>
      ))}
    </span>
  )
}
