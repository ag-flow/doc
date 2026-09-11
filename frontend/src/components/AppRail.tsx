import { useNavigate, useMatch, NavLink } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  NewspaperClipping, SquaresFour, Tag, Stack, FileText, WebhooksLogo, Lightning,
  UserCircle, FileCode, Password, Layout, UsersThree, Key, ShieldCheck, Broadcast,
  PlugsConnected, Paperclip, SignOut, type Icon,
} from '@phosphor-icons/react'
import { api, clearToken, isSuperAdmin } from '../lib/api'

/**
 * Rail de navigation : encre pleine, 56px, icônes duotone sans libellé
 * permanent (infobulle au survol). Groupe du haut = workspace courant,
 * groupe du bas = administration, séparés par un filet.
 */

const ICON = 20

function Tip({ children }: { children: string }) {
  return <span className="rail-tip">{children}</span>
}

interface ItemProps {
  /** Absent quand l'entrée est désactivée : il n'y a alors nulle part où aller. */
  to?: string
  icon: Icon
  label: string
  end?: boolean
  /** Cible indisponible dans le contexte courant (ex. documents sans bloc). */
  disabled?: boolean
}

function RailItem({ to, icon: Ico, label, end = false, disabled = false }: ItemProps) {
  if (disabled || !to) {
    return (
      <span className="rail-btn" aria-disabled="true" title={label}>
        <Ico size={ICON} weight="duotone" />
        <Tip>{label}</Tip>
      </span>
    )
  }
  return (
    <NavLink to={to} end={end} title={label} className="rail-btn">
      <Ico size={ICON} weight="duotone" />
      <Tip>{label}</Tip>
    </NavLink>
  )
}

export function AppRail() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const superAdmin = isSuperAdmin()

  const wsSlug = useMatch('/ws/:wsSlug/*')?.params.wsSlug ?? null
  const blocSlug = useMatch('/ws/:wsSlug/blocs/:blocSlug/*')?.params.blocSlug ?? null

  async function logout() {
    // Révoque la session EN BASE côté serveur (un cookie copié cesse de valoir),
    // puis efface le cookie et l'indice d'UI. Best-effort : on nettoie et redirige
    // même si l'appel échoue (hors ligne).
    try {
      await api.post('/auth/logout', {})
    } catch {
      /* ignore : on nettoie côté client de toute façon */
    }
    clearToken()
    queryClient.clear()
    void navigate('/login')
  }

  return (
    <aside className="rail" data-testid="app-rail">
      <NavLink to="/workspaces" title="docflow" className="rail-btn rail-brand" end>
        <NewspaperClipping size={22} weight="duotone" />
        <Tip>docflow</Tip>
      </NavLink>
      <div className="rail-rule mb-2" />

      <div className="rail-group">
        <RailItem to="/workspaces" icon={SquaresFour} label="Workspaces" end />
        {wsSlug && (
          <>
            <RailItem to={`/ws/${wsSlug}/types`} icon={Tag} label="Types fonctionnels" />
            <RailItem to={`/ws/${wsSlug}/blocs`} icon={Stack} label="Blocs" end />
            {blocSlug ? (
              <RailItem
                to={`/ws/${wsSlug}/blocs/${blocSlug}/documents`}
                icon={FileText}
                label="Documents"
              />
            ) : (
              <RailItem icon={FileText} label="Documents (choisir un bloc)" disabled />
            )}
            <RailItem to={`/ws/${wsSlug}/webhooks`} icon={WebhooksLogo} label="Webhooks" />
          </>
        )}
      </div>

      <div className="flex-1" />

      <div className="rail-rule my-2" />
      <div className="rail-group">
        <RailItem to="/me" icon={UserCircle} label="Mon profil" />
        <RailItem to="/contracts" icon={FileCode} label="Contrats OpenAPI" />
        <RailItem to="/api-keys" icon={Password} label="Clés API" />
        {superAdmin && (
          <>
            {/* Objets d'instance : un automate couvre plusieurs workspaces. */}
            <RailItem to="/automations" icon={Lightning} label="Automates" />
            <RailItem to="/templates" icon={Layout} label="Templates" />
            <RailItem to="/admin/users" icon={UsersThree} label="Utilisateurs" />
            <RailItem to="/admin/artifact-types" icon={Paperclip} label="Types d'artefact" />
            <RailItem to="/admin/vault" icon={Key} label="Wallets Vault" />
            <RailItem to="/admin/oidc" icon={ShieldCheck} label="Config OIDC" />
            <RailItem to="/admin/events-producer" icon={Broadcast} label="Connexion workflow" />
            <RailItem to="/admin/remote" icon={PlugsConnected} label="Connexions & Sauvegarde" />
          </>
        )}
        <button type="button" onClick={logout} title="Déconnexion" className="rail-btn">
          <SignOut size={ICON} weight="duotone" />
          <Tip>Déconnexion</Tip>
        </button>
      </div>
    </aside>
  )
}
