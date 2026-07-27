import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, type AppUserOut } from '../lib/api'
import { Button } from '../components/ui/button'
import { SectionHead } from '../components/SectionHead'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState, ErrorLine, TableSkeleton } from '../components/ui/states'
import { relativeDate } from '../lib/relativeDate'

function StatusTag({ user }: { user: AppUserOut }) {
  if (user.disabled) return <span className="tag tag-accent-2">désactivé</span>
  if (!user.validated) return <span className="tag tag-outline">en attente</span>
  return <span className="tag tag-accent">actif</span>
}

/** Droits par rôle, en lecture — la vérité vit dans le backend (RBAC). */
const ROLES: { role: string; rights: string }[] = [
  {
    role: 'Administrateur',
    rights:
      "Accès à tous les workspaces, gestion des comptes, des templates, du vault, de l'OIDC, "
      + 'des connexions et des sauvegardes. Le dernier administrateur local connectable est '
      + 'protégé : il ne peut être ni rétrogradé, ni désactivé, ni supprimé (anti-lock-out).',
  },
  {
    role: 'Utilisateur',
    rights:
      'Accès aux workspaces dont il est membre ou propriétaire : documents, blocs, types, '
      + "automates et webhooks de ces workspaces. Aucun accès à l'administration de l'instance.",
  },
]

export function UsersAdmin() {
  const qc = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<AppUserOut | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  const { data: users = [], isLoading } = useQuery<AppUserOut[]>({
    queryKey: ['admin-users'],
    queryFn: () => usersApi.list(),
  })

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['admin-users'] })
  const onError = (e: Error) => setApiError(e.message)

  const validateMut = useMutation({
    mutationFn: (id: string) => usersApi.validate(id),
    onSuccess: invalidate,
    onError,
  })
  const unvalidateMut = useMutation({
    mutationFn: (id: string) => usersApi.unvalidate(id),
    onSuccess: invalidate,
    onError,
  })
  // Rôle et activation : le garde anti-lock-out du backend répond 409 si
  // l'opération retirerait le dernier accès administrateur — l'erreur s'affiche.
  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { is_admin?: boolean; disabled?: boolean } }) =>
      usersApi.update(id, body),
    onSuccess: () => { setApiError(null); invalidate() },
    onError,
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => usersApi.delete(id),
    onSuccess: () => { setDeleteTarget(null); invalidate() },
    onError,
  })

  const pending = users.filter((u) => !u.validated && !u.disabled)
  const rest = users.filter((u) => u.validated || u.disabled)
  const busy = validateMut.isPending || unvalidateMut.isPending || updateMut.isPending

  function row(user: AppUserOut, isPending: boolean) {
    return (
      <tr key={user.id} data-testid={`user-row-${user.id}`}>
        <td>
          <span className="block text-[15px] font-[600] [font-family:var(--font-heading)]">
            {user.label}
            {user.username && user.username !== user.label && (
              <span className="ml-2 text-[12px] font-normal text-ink/[0.45] [font-family:var(--font-mono)]">
                @{user.username}
              </span>
            )}
          </span>
          <span className="block text-[12px] text-ink/[0.55]">{user.email}</span>
        </td>
        <td data-testid={`user-role-${user.id}`}>
          {user.is_admin
            ? <span className="tag tag-accent">admin</span>
            : <span className="tag tag-neutral">utilisateur</span>}
          <span className="ml-1.5 text-[11px] text-ink/[0.45]">{user.source}</span>
        </td>
        <td className="text-ink/[0.6]" data-testid={`user-ws-${user.id}`}>
          {user.is_admin ? 'tous' : user.workspaces_count}
        </td>
        <td className="text-ink/[0.55]" data-testid={`user-login-${user.id}`}>
          {user.last_login_at ? relativeDate(user.last_login_at) : 'jamais'}
        </td>
        <td><StatusTag user={user} /></td>
        <td className="whitespace-nowrap text-right">
          {isPending ? (
            <Button size="sm" onClick={() => validateMut.mutate(user.id)} disabled={busy}
              data-testid={`validate-${user.id}`}>
              Valider
            </Button>
          ) : (
            <>
              <Button variant="ghost" size="sm" disabled={busy}
                onClick={() => updateMut.mutate({ id: user.id, body: { is_admin: !user.is_admin } })}
                data-testid={`toggle-role-${user.id}`}>
                {user.is_admin ? 'Rétrograder' : 'Promouvoir admin'}
              </Button>
              {user.validated && !user.is_admin && (
                <Button variant="ghost" size="sm" disabled={busy}
                  onClick={() => unvalidateMut.mutate(user.id)}>
                  Révoquer
                </Button>
              )}
              <Button variant="ghost" size="sm" disabled={busy}
                onClick={() => updateMut.mutate({ id: user.id, body: { disabled: !user.disabled } })}
                data-testid={`toggle-disabled-${user.id}`}>
                {user.disabled ? 'Réactiver' : 'Désactiver'}
              </Button>
              <Button variant="ghost" size="sm" className="text-accent-2-700" disabled={busy}
                onClick={() => setDeleteTarget(user)} data-testid={`delete-${user.id}`}>
                Supprimer
              </Button>
            </>
          )}
        </td>
      </tr>
    )
  }

  const head = (
    <thead>
      <tr>
        <th>Personne</th>
        <th>Rôle</th>
        <th>Workspaces</th>
        <th>Dernière connexion</th>
        <th>État</th>
        <th />
      </tr>
    </thead>
  )

  return (
    <div className="mx-auto max-w-[1100px] px-6 pt-11 pb-24">
      <SectionHead kicker="Administration" title="Utilisateurs" />
      <p className="mb-8 max-w-[64ch] text-[16px] leading-[1.6] text-ink/[0.68]">
        Les utilisateurs qui se connectent via Keycloak arrivent en attente de validation :
        validez-les pour leur donner accès. L'accès aux contenus se donne workspace par
        workspace (membre ou propriétaire) ; un administrateur voit tout.
      </p>

      <ErrorLine message={apiError} testId="users-api-error" />

      {isLoading ? (
        <TableSkeleton rows={5} columns={5} />
      ) : (
        <>
          {pending.length > 0 && (
            <section className="mb-10">
              <h6 className="mb-2 text-accent-2-700">
                En attente de validation ({pending.length})
              </h6>
              <table className="table" data-testid="pending-users">
                {head}
                <tbody>{pending.map((u) => row(u, true))}</tbody>
              </table>
            </section>
          )}

          <section>
            <h6 className="mb-2 text-ink/[0.5]">Tous les utilisateurs ({rest.length})</h6>
            {rest.length === 0 ? (
              <EmptyState testId="users-empty" message="Aucun utilisateur." />
            ) : (
              <table className="table" data-testid="all-users">
                {head}
                <tbody>{rest.map((u) => row(u, false))}</tbody>
              </table>
            )}
          </section>

          {/* ── Rôles, en lecture — séparés par du blanc, pas de carte. ── */}
          <section className="mt-14" data-testid="roles-section">
            <h6 className="mb-2 text-ink/[0.5]">Rôles</h6>
            <div className="grid max-w-[900px] gap-6 sm:grid-cols-2">
              {ROLES.map((r) => (
                <div key={r.role}>
                  <h5 className="mb-1">{r.role}</h5>
                  <p className="m-0 text-[14px] leading-[1.6] text-ink/[0.65]">{r.rights}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {deleteTarget && (
        <ConfirmDialog
          testId="user-delete-dialog"
          title="Supprimer le compte"
          message={`Supprimer le compte de « ${deleteTarget.label} » (${deleteTarget.email}) ? Ses préférences et appartenances aux workspaces partent avec lui.`}
          confirmLabel="Supprimer le compte"
          pending={deleteMut.isPending}
          error={apiError}
          onConfirm={() => deleteMut.mutate(deleteTarget.id)}
          onCancel={() => { setDeleteTarget(null); setApiError(null) }}
        />
      )}
    </div>
  )
}
