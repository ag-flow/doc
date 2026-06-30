import { useNavigate, useMatch, NavLink } from 'react-router-dom'
import {
  Layers,
  LayoutTemplate,
  LayoutDashboard,
  Tags,
  Boxes,
  FileText,
  Webhook,
  HardDrive,
  KeyRound,
  KeySquare,
  ShieldCheck,
  LogOut,
  Zap,
  Users,
} from 'lucide-react'
import { clearToken, isSuperAdmin } from '../lib/api'

interface NavItemProps {
  to: string
  icon: React.ElementType
  label: string
  disabled?: boolean
  end?: boolean
}

function NavItem({ to, icon: Icon, label, disabled = false, end = false }: NavItemProps) {
  if (disabled) {
    return (
      <div
        className="group relative flex h-10 w-10 items-center justify-center rounded-lg text-gray-600 cursor-not-allowed"
        title={label}
      >
        <Icon size={18} />
        <Tooltip>{label}</Tooltip>
      </div>
    )
  }
  return (
    <NavLink
      to={to}
      end={end}
      title={label}
      className={({ isActive }) =>
        `group relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
          isActive
            ? 'bg-indigo-600 text-white'
            : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100'
        }`
      }
    >
      <Icon size={18} />
      <Tooltip>{label}</Tooltip>
    </NavLink>
  )
}

function Tooltip({ children }: { children: string }) {
  return (
    <span className="pointer-events-none absolute left-full z-50 ml-3 hidden whitespace-nowrap rounded-md bg-gray-900 border border-gray-700 px-2.5 py-1.5 text-xs font-medium text-gray-100 shadow-lg group-hover:block">
      {children}
    </span>
  )
}

function Divider() {
  return <div className="mx-auto my-1 h-px w-6 bg-gray-700" />
}

export function Sidebar() {
  const navigate = useNavigate()
  const superAdmin = isSuperAdmin()

  const wsMatch = useMatch('/ws/:wsSlug/*')
  const wsSlug = wsMatch?.params.wsSlug ?? null

  const blocMatch = useMatch('/ws/:wsSlug/blocs/:blocSlug/*')
  const blocSlug = blocMatch?.params.blocSlug ?? null

  function logout() {
    clearToken()
    void navigate('/login')
  }

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-14 flex-col items-center bg-gray-950 py-3">
      {/* Logo */}
      <NavLink
        to="/workspaces"
        title="docflow"
        className="group relative mb-2 flex h-10 w-10 items-center justify-center rounded-lg text-indigo-400 hover:text-indigo-300"
      >
        <Layers size={22} />
        <Tooltip>docflow</Tooltip>
      </NavLink>

      {/* Navigation globale */}
      <div className="flex flex-col items-center gap-1">
        <NavItem to="/workspaces" icon={LayoutDashboard} label="Workspaces" end />
      </div>

      {/* Navigation workspace (contextuelle) */}
      {wsSlug && (
        <>
          <Divider />
          <div className="flex flex-col items-center gap-1">
            <NavItem to={`/ws/${wsSlug}/types`} icon={Tags} label="Types fonctionnels" />
            <NavItem to={`/ws/${wsSlug}/blocs`} icon={Boxes} label="Blocs" end />
            {blocSlug ? (
              <NavItem
                to={`/ws/${wsSlug}/blocs/${blocSlug}/documents`}
                icon={FileText}
                label="Documents"
              />
            ) : (
              <NavItem
                to={`/ws/${wsSlug}/blocs`}
                icon={FileText}
                label="Documents (choisir un bloc)"
                disabled
              />
            )}
            <NavItem to={`/ws/${wsSlug}/webhooks`} icon={Webhook} label="Webhooks" />
            <NavItem to={`/ws/${wsSlug}/automations`} icon={Zap} label="Automates" />
          </div>
        </>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Clés API — accessible à tous les utilisateurs */}
      <div className="flex flex-col items-center gap-1 mb-1">
        <NavItem to="/api-keys" icon={KeySquare} label="Clés API" />
      </div>

      {/* Section admin (bas) */}
      {superAdmin && (
        <>
          <Divider />
          <div className="flex flex-col items-center gap-1 mb-1">
            <NavItem to="/templates" icon={LayoutTemplate} label="Templates" />
            <NavItem to="/admin/users" icon={Users} label="Utilisateurs" />
            <NavItem to="/admin/vault" icon={KeyRound} label="Wallets Vault" />
            <NavItem to="/admin/oidc" icon={ShieldCheck} label="Config OIDC" />
            <NavItem to="/admin/remote" icon={HardDrive} label="Connexions & Sauvegarde" />
          </div>
        </>
      )}

      <button
        onClick={logout}
        title="Déconnexion"
        className="group relative flex h-10 w-10 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-800 hover:text-red-400"
      >
        <LogOut size={18} />
        <Tooltip>Déconnexion</Tooltip>
      </button>
    </aside>
  )
}
