import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './lib/i18n'
import { getToken } from './lib/api'
import { WorkspaceProvider } from './contexts/WorkspaceContext'
import { Sidebar } from './components/Sidebar'
import { Login } from './pages/Login'
import TemplateList from './pages/TemplateList'
import WorkspaceList from './pages/WorkspaceList'
import { WorkspaceLayout } from './pages/WorkspaceLayout'
import { TypesAdmin } from './pages/TypesAdmin'
import { BlocsAdmin } from './pages/BlocsAdmin'
import { BlockDocumentList } from './pages/BlockDocumentList'
import { DocumentEditor } from './pages/DocumentEditor'
import { WebhooksAdmin } from './pages/WebhooksAdmin'
import { OidcAdmin } from './pages/OidcAdmin'
import { VaultAdmin } from './pages/VaultAdmin'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Layout principal : sidebar fixe à gauche + contenu scrollable. */
function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="ml-14 flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}

const router = createBrowserRouter([
  { path: '/login', element: <Login /> },

  {
    path: '/templates',
    element: (
      <ProtectedRoute>
        <AppLayout><TemplateList /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/workspaces',
    element: (
      <ProtectedRoute>
        <AppLayout><WorkspaceList /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/ws/:wsSlug',
    element: (
      <ProtectedRoute>
        <AppLayout><WorkspaceLayout /></AppLayout>
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <Navigate to="blocs" replace /> },
      { path: 'types', element: <TypesAdmin /> },
      { path: 'blocs', element: <BlocsAdmin /> },
      { path: 'blocs/:blocSlug/documents', element: <BlockDocumentList /> },
      { path: 'blocs/:blocSlug/documents/:docId', element: <DocumentEditor /> },
      { path: 'webhooks', element: <WebhooksAdmin /> },
    ],
  },
  {
    path: '/admin/vault',
    element: (
      <ProtectedRoute>
        <AppLayout><VaultAdmin /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/admin/oidc',
    element: (
      <ProtectedRoute>
        <AppLayout><OidcAdmin /></AppLayout>
      </ProtectedRoute>
    ),
  },
  { path: '/', element: <Navigate to="/workspaces" replace /> },
  { path: '*', element: <Navigate to="/workspaces" replace /> },
])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WorkspaceProvider>
        <RouterProvider router={router} />
      </WorkspaceProvider>
    </QueryClientProvider>
  )
}
