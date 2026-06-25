import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import './lib/i18n'
import { getToken, clearToken } from './lib/api'
import { WorkspaceProvider, useWorkspace } from './contexts/WorkspaceContext'
import { Login } from './pages/Login'
import WorkspaceList from './pages/WorkspaceList'
import { TypesAdmin } from './pages/TypesAdmin'
import { DocumentTree } from './pages/DocumentTree'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

function NavBar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { currentSlug } = useWorkspace()
  return (
    <nav className="flex items-center gap-6 border-b border-gray-200 bg-white px-8 py-3">
      <Link to="/workspaces" className="font-semibold text-indigo-600">docflow</Link>
      <Link to="/workspaces" className="text-sm text-gray-600 hover:text-gray-900">
        {t('nav.workspaces')}
      </Link>
      {currentSlug && (
        <>
          <Link
            to={`/workspaces/${currentSlug}/types`}
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            {t('nav.types')}
          </Link>
          <Link
            to={`/workspaces/${currentSlug}/documents`}
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            {t('nav.documents')}
          </Link>
        </>
      )}
      <div className="ml-auto">
        <button
          className="text-sm text-gray-500 hover:text-red-600"
          onClick={() => { clearToken(); void navigate('/login') }}
        >
          {t('nav.logout')}
        </button>
      </div>
    </nav>
  )
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <main>{children}</main>
    </div>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/workspaces"
        element={
          <ProtectedRoute>
            <Layout><WorkspaceList /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/workspaces/:ws/types"
        element={
          <ProtectedRoute>
            <Layout><TypesAdmin /></Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/workspaces/:ws/documents"
        element={
          <ProtectedRoute>
            <Layout><DocumentTree /></Layout>
          </ProtectedRoute>
        }
      />
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
