import { useState } from 'react'
import {
  Navigate,
  NavLink,
  Outlet,
  useNavigate,
  useOutletContext,
  useParams,
  useMatch,
} from 'react-router-dom'
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
  const navigate = useNavigate()
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const { data: workspace, isLoading, isError } = useQuery<WorkspaceOut>({
    queryKey: ['workspace', wsSlug],
    queryFn: () => api.get<WorkspaceOut>(`/workspaces/${wsSlug}`),
    retry: false,
  })

  const { data: allWorkspaces = [] } = useQuery<WorkspaceOut[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceOut[]>('/workspaces'),
  })

  // Détecter la section courante pour la conserver lors du switch workspace
  const inTypes = Boolean(useMatch('/ws/:wsSlug/types'))
  const inBlocs = Boolean(useMatch('/ws/:wsSlug/blocs'))
  const inBlocDocs = Boolean(useMatch('/ws/:wsSlug/blocs/:blocSlug/documents/*'))
  const inDocEditor = Boolean(useMatch('/ws/:wsSlug/blocs/:blocSlug/documents/:docId'))
  const inBlocAny = inBlocs || inBlocDocs || inDocEditor

  // Détecter si on est dans un bloc précis (pour activer l'onglet Documents + garde)
  const blocMatch = useMatch('/ws/:wsSlug/blocs/:blocSlug/*')
  const blocSlugInUrl = blocMatch?.params.blocSlug ?? null

  const currentSection = inTypes ? 'types' : inBlocAny ? 'blocs' : 'blocs'

  // Garde bloc : si on est sur une route de bloc, vérifier qu'il existe
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

  // Si le bloc demandé n'existe pas → retour à la liste des blocs
  if (blocSlugInUrl && !blocsLoading && (blocsError || (blocs && !blocs.some((b) => b.slug === blocSlugInUrl)))) {
    return <Navigate to={`/ws/${wsSlug}/blocs`} replace />
  }

  const activeWorkspaces = allWorkspaces.filter((w) => !w.archived_at)

  function switchWorkspace(slug: string) {
    const section = currentSection === 'types' ? 'types' : 'blocs'
    void navigate(`/ws/${slug}/${section}`)
    setDropdownOpen(false)
  }

  return (
    <div className="min-h-screen bg-gray-50" data-testid="workspace-layout">
      {/* Fil d'Ariane */}
      <div className="border-b border-gray-100 bg-white px-8 py-2 text-sm text-gray-500">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-indigo-600">docflow</span>
          <span>›</span>
          {/* Dropdown workspace */}
          <div className="relative">
            <button
              className="flex items-center gap-1 font-medium text-gray-800 hover:text-indigo-600"
              onClick={() => setDropdownOpen((v) => !v)}
              data-testid="ws-dropdown-btn"
            >
              {workspace.label}
              <span className="text-xs">▾</span>
            </button>
            {dropdownOpen && (
              <div
                className="absolute left-0 z-20 mt-1 min-w-48 rounded border border-gray-200 bg-white shadow-lg"
                data-testid="ws-dropdown-menu"
              >
                <button
                  className="block w-full px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-50"
                  onClick={() => { setDropdownOpen(false); void navigate('/workspaces') }}
                  data-testid="ws-switch-all"
                >
                  {t('nav.allWorkspaces')}
                </button>
                <div className="my-1 border-t border-gray-100" />
                {activeWorkspaces.map((w) => (
                  <button
                    key={w.slug}
                    className={`block w-full px-4 py-2 text-left text-sm hover:bg-gray-50 ${
                      w.slug === wsSlug ? 'font-medium text-indigo-600' : 'text-gray-700'
                    }`}
                    onClick={() => switchWorkspace(w.slug)}
                    data-testid={`ws-switch-${w.slug}`}
                  >
                    {w.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sous-onglets */}
      <nav
        className="flex gap-1 border-b border-gray-200 bg-white px-8"
        data-testid="ws-tabs"
      >
        <NavLink
          to={`/ws/${wsSlug}/types`}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              isActive
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-600 hover:text-gray-900'
            }`
          }
          data-testid="tab-types"
        >
          {t('nav.types')}
        </NavLink>
        <NavLink
          to={`/ws/${wsSlug}/blocs`}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              isActive || inBlocAny
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-600 hover:text-gray-900'
            }`
          }
          end
          data-testid="tab-blocs"
        >
          {t('nav.blocs')}
        </NavLink>
        {/* Onglet Documents : actif si on est dans un bloc */}
        {blocSlugInUrl ? (
          <NavLink
            to={`/ws/${wsSlug}/blocs/${blocSlugInUrl}/documents`}
            className={({ isActive }) =>
              `-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
                isActive
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`
            }
            data-testid="tab-documents"
          >
            {t('nav.documents')}
          </NavLink>
        ) : (
          <span
            className="-mb-px border-b-2 border-transparent px-4 py-2 text-sm font-medium text-gray-300 cursor-not-allowed"
            title={t('nav.chooseBloc')}
            data-testid="tab-documents-disabled"
          >
            {t('nav.documents')}
          </span>
        )}
        <NavLink
          to={`/ws/${wsSlug}/webhooks`}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              isActive
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-600 hover:text-gray-900'
            }`
          }
          data-testid="tab-webhooks"
        >
          {t('webhooks.title')}
        </NavLink>
      </nav>

      <main>
        <Outlet context={{ workspace } satisfies WorkspaceLayoutContext} />
      </main>
    </div>
  )
}
