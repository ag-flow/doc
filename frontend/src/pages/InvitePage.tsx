import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { inviteApi } from '../lib/api'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Field } from '../components/ui/field'

/**
 * Page publique d'une invitation : l'invité voit pour qui est le lien et
 * définit son mot de passe. Jeton inconnu, utilisé ou expiré → même message
 * (aucun oracle sur l'existence d'un compte).
 */
export function InvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const { data: info, isLoading, isError } = useQuery({
    queryKey: ['invite', token],
    queryFn: () => inviteApi.info(token!),
    enabled: Boolean(token),
    retry: false,
  })

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 12) {
      setError('Le mot de passe doit faire au moins 12 caractères.')
      return
    }
    if (password !== confirm) {
      setError('Les deux saisies ne correspondent pas.')
      return
    }
    setSubmitting(true)
    try {
      await inviteApi.accept(token!, password)
      void navigate('/login')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper">
      <div className="w-full max-w-[340px] px-6" data-testid="invite-page">
        {isLoading ? null : isError || !info ? (
          <>
            <h3 className="mb-1">Invitation introuvable</h3>
            <p className="text-[14px] text-ink/[0.6]" data-testid="invite-invalid">
              Ce lien d'invitation est inconnu, déjà utilisé ou expiré. Demandez un
              nouveau lien à votre administrateur.
            </p>
          </>
        ) : (
          <>
            <h3 className="mb-1">Bienvenue, {info.label}</h3>
            <p className="mb-6 text-[13px] text-ink/[0.6]">
              Choisissez le mot de passe du compte <strong>{info.email}</strong>.
            </p>
            <form onSubmit={submit} className="grid gap-3.5">
              <Field label="Mot de passe" htmlFor="invite-password"
                hint="12 caractères minimum.">
                <Input
                  id="invite-password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setError(null) }}
                  autoFocus
                  required
                  data-testid="invite-password"
                />
              </Field>
              <Field label="Confirmer" htmlFor="invite-confirm" error={error}>
                <Input
                  id="invite-confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => { setConfirm(e.target.value); setError(null) }}
                  required
                  aria-invalid={error ? 'true' : undefined}
                  data-testid="invite-confirm"
                />
              </Field>
              <Button type="submit" block disabled={submitting} data-testid="invite-submit">
                {submitting ? 'Création…' : 'Créer mon accès'}
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
