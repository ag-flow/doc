import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import './lib/i18n'
import { getToken, clearToken } from './lib/api'
import { WorkspaceProvider } from './contexts/WorkspaceContext'
import { Login } from './pages/Login'
import TemplateList from './pages/TemplateList'
import WorkspaceList from './pages/WorkspaceList'
import { WorkspaceLayout } from './pages/WorkspaceLayout'
import { TypesAdmin } from './pages/TypesAdmin'
import { BlocsAdmin } from './pages/BlocsAdmin'
import { BlockDocumentList } from './pages/BlockDocumentList'
import { DocumentEditor } from './pages/DocumentEditor'
import { WebhooksAdmin } from './pages/WebhooksAdmin'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Barre globale : logo, liens globaux, logout. */
function GlobalNav() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <nav className="flex items-center gap-6 border-b border-gray-200 bg-white px-8 py-3">
      <Link to="/workspaces" className="font-semibold text-indigo-600">
        docflow
      </Link>
      <Link to="/templates" className="text-sm text-gray-600 hover:text-gray-900">
        {t('nav.templates')}
      </Link>
      <Link to="/workspaces" className="text-sm text-gray-600 hover:text-gray-900">
        {t('nav.workspaces')}
      </Link>
      <div className="ml-auto">
        <button
          className="text-sm text-gray-500 hover:text-red-600"
          onClick={() => {
            clearToken()
            void navigate('/login')
          }}
        >
          {t('nav.logout')}
        </button>
      </div>
    </nav>
  )
}

function GlobalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <GlobalNav />
      <main>{children}</main>
    </div>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* Routes globales */}
      <Route path="/templates" element={<GlobalLayout><TemplateList /></GlobalLayout>} />
      <Route
        path="/workspaces"
        element={
          <ProtectedRoute>
            <GlobalLayout><WorkspaceList /></GlobalLayout>
          </ProtectedRoute>
        }
      />

      {/* Routes workspace — toutes sous le WorkspaceLayout contextuel */}
      <Route
        path="/ws/:wsSlug"
        element={
          <ProtectedRoute>
            <GlobalLayout>
              <WorkspaceLayout />
            </GlobalLayout>
          </ProtectedRoute>
        }
      >
        {/* /ws/:wsSlug → redirect vers blocs */}
        <Route index element={<Navigate to="blocs" replace />} />
        <Route path="types" element={<TypesAdmin />} />
        <Route path="blocs" element={<BlocsAdmin />} />
        <Route path="blocs/:blocSlug/documents" element={<BlockDocumentList />} />
        <Route path="blocs/:blocSlug/documents/:docId" element={<DocumentEditor />} />
        <Route path="webhooks" element={<WebhooksAdmin />} />
      </Route>

      {/* Racine + catch-all */}
      <Route path="/" element={<Navigate to="/workspaces" replace />} />
      <Route path="*" element={<Navigate to="/workspaces" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <WorkspaceProvider>
          <AppRoutes />
        </WorkspaceProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
