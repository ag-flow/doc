import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './lib/i18n'
import { getToken } from './lib/api'
import { WorkspaceProvider } from './contexts/WorkspaceContext'
import { ToastProvider } from './components/Toast'
import { AppRail } from './components/AppRail'
import { AppHeader } from './components/AppHeader'
import { PublicDocumentViewer } from './pages/PublicDocumentViewer'
import { Login } from './pages/Login'
import { OidcCallback } from './pages/OidcCallback'
import TemplateList from './pages/TemplateList'
import WorkspaceList from './pages/WorkspaceList'
import { WorkspaceLayout } from './pages/WorkspaceLayout'
import { TypesAdmin } from './pages/TypesAdmin'
import { BlocsAdmin } from './pages/BlocsAdmin'
import { BlockDocumentList } from './pages/BlockDocumentList'
import { DocumentEditor } from './pages/DocumentEditor'
import { WebhooksAdmin } from './pages/WebhooksAdmin'
import { OidcAdmin } from './pages/OidcAdmin'
import { EventsProducerAdmin } from './pages/EventsProducerAdmin'
import { VaultAdmin } from './pages/VaultAdmin'
import { AutomatesPage } from './pages/AutomatesPage'
import { UsersAdmin } from './pages/UsersAdmin'
import { ApiKeysPage } from './pages/ApiKeysPage'
import { RemotePage } from './pages/RemotePage'
import { ContractsAdmin } from './pages/ContractsAdmin'
import { MyProfilePage } from './pages/MyProfilePage'
import { DesignSystemPage } from './pages/DesignSystemPage'
import { InvitePage } from './pages/InvitePage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Layout principal : rail fixe à gauche, en-tête collé, contenu scrollable.
 *  La marge gauche suit `--rail-width` — pas une classe d'espacement, qui
 *  dériverait de la largeur du rail au premier changement de densité. */
function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-paper">
      <AppRail />
      <div
        className="flex flex-1 flex-col overflow-hidden"
        style={{ marginLeft: 'var(--rail-width)' }}
      >
        <AppHeader />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}

const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  { path: '/oidc/callback', element: <OidcCallback /> },

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
      { path: 'automations', element: <AutomatesPage /> },
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
  {
    path: '/admin/events-producer',
    element: (
      <ProtectedRoute>
        <AppLayout><EventsProducerAdmin /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/admin/users',
    element: (
      <ProtectedRoute>
        <AppLayout><UsersAdmin /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/api-keys',
    element: (
      <ProtectedRoute>
        <AppLayout><ApiKeysPage /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/me',
    element: (
      <ProtectedRoute>
        <AppLayout><MyProfilePage /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/contracts',
    element: (
      <ProtectedRoute>
        <AppLayout><ContractsAdmin /></AppLayout>
      </ProtectedRoute>
    ),
  },
  {
    path: '/admin/remote',
    element: (
      <ProtectedRoute>
        <AppLayout><RemotePage /></AppLayout>
      </ProtectedRoute>
    ),
  },
  // Référence interne du système de design : hors navigation, route directe.
  {
    path: '/design-system',
    element: (
      <ProtectedRoute>
        <DesignSystemPage />
      </ProtectedRoute>
    ),
  },
  { path: '/pub/:docId', element: <PublicDocumentViewer /> },
  // Invitation : page publique (l'invité n'a pas encore de compte utilisable).
  { path: '/invite/:token', element: <InvitePage /> },
  { path: '/', element: <Navigate to="/workspaces" replace /> },
  { path: '*', element: <Navigate to="/workspaces" replace /> },
])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <WorkspaceProvider>
          <RouterProvider router={router} />
        </WorkspaceProvider>
      </ToastProvider>
    </QueryClientProvider>
  )
}
