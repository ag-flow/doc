import { useEffect } from 'react'
import { Navigate, Outlet, useOutletContext, useParams, useMatch } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, docsApi, type WorkspaceOut, type DataBlockOut } from '../lib/api'
import { useChangeFeed } from '../hooks/useChangeFeed'
import { useWorkspace } from '../contexts/WorkspaceContext'

interface WorkspaceLayoutContext {
  workspace: WorkspaceOut
}

export function useWorkspaceCtx(): WorkspaceLayoutContext {
  return useOutletContext<WorkspaceLayoutContext>()
}

export function WorkspaceLayout() {
  const { wsSlug } = useParams<{ wsSlug: string }>()
  const { t } = useTranslation()

  // Le contexte workspace suit la ROUTE, pas seulement les clics dans la liste des
  // workspaces : une arrivée par Cmd+K, lien direct ou F5 laissait sinon le slug
  // d'une session précédente, et les blocs dataset / puces artefact / liens
  // `artifact://` interrogeaient l'API sur le mauvais workspace (404).
  const { currentSlug, setCurrentSlug } = useWorkspace()
  useEffect(() => {
    if (wsSlug && wsSlug !== currentSlug) setCurrentSlug(wsSlug)
  }, [wsSlug, currentSlug, setCurrentSlug])

  // Les autres sessions (UI, agents MCP, automates) peuvent faire évoluer le
  // contenu et le modèle : suivre le change feed et invalider les caches.
  useChangeFeed(wsSlug)

  const { data: workspace, isLoading, isError } = useQuery<WorkspaceOut>({
    queryKey: ['workspace', wsSlug],
    queryFn: () => api.get<WorkspaceOut>(`/workspaces/${wsSlug}`),
    retry: false,
  })

  // Garde bloc : si on est sur une route de bloc, vérifier qu'il existe
  const blocMatch = useMatch('/ws/:wsSlug/blocs/:blocSlug/*')
  const blocSlugInUrl = blocMatch?.params.blocSlug ?? null

  const { data: blocs, isLoading: blocsLoading, isError: blocsError } = useQuery<DataBlockOut[]>({
    queryKey: ['blocs', wsSlug],
    queryFn: () => docsApi.getBlocks(wsSlug!),
    enabled: Boolean(wsSlug && blocSlugInUrl),
  })

  if (isLoading || (blocSlugInUrl && blocsLoading)) {
    return <div className="p-8 text-gray-500" data-testid="ws-loading">{t('common.loading')}</div>
  }

  if (isError || !workspace) {
    return <Navigate to="/workspaces" state={{ invalidWs: wsSlug }} replace />
  }

  if (workspace.archived_at) {
    return <Navigate to="/workspaces" state={{ archivedWs: wsSlug }} replace />
  }

  if (
    blocSlugInUrl &&
    !blocsLoading &&
    (blocsError || (blocs && !blocs.some((b) => b.slug === blocSlugInUrl)))
  ) {
    return <Navigate to={`/ws/${wsSlug}/blocs`} replace />
  }

  // Tant que le contexte n'a pas rattrapé la route, ne pas monter le contenu : les
  // blocs enfants liraient le slug précédent et déclencheraient des requêtes dessus.
  if (wsSlug && currentSlug !== wsSlug) {
    return <div className="p-8 text-gray-500" data-testid="ws-loading">{t('common.loading')}</div>
  }

  return (
    <div data-testid="workspace-layout">
      <Outlet context={{ workspace } satisfies WorkspaceLayoutContext} />
    </div>
  )
}
