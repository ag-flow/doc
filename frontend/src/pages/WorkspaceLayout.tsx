import { Navigate, Outlet, useOutletContext, useParams, useMatch } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api, docsApi, type WorkspaceOut, type DataBlockOut } from '../lib/api'

interface WorkspaceLayoutContext {
  workspace: WorkspaceOut
}

export function useWorkspaceCtx(): WorkspaceLayoutContext {
  return useOutletContext<WorkspaceLayoutContext>()
}

export function WorkspaceLayout() {
  const { wsSlug } = useParams<{ wsSlug: string }>()
  const { t } = useTranslation()

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

  return (
    <div data-testid="workspace-layout">
      <Outlet context={{ workspace } satisfies WorkspaceLayoutContext} />
    </div>
  )
}
