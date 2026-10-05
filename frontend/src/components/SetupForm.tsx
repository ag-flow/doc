import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { setupApi, setToken, api } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Field } from './ui/field'

const schema = z
  .object({
    username: z
      .string()
      .min(2, 'Minimum 2 caractères')
      .max(50, 'Maximum 50 caractères')
      .regex(/^[a-zA-Z0-9_.\-]+$/, 'Lettres, chiffres, _, ., - uniquement'),
    email: z.string().email('Email invalide'),
    password: z.string().min(8, 'Minimum 8 caractères'),
    confirm_password: z.string(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: 'Les mots de passe ne correspondent pas',
    path: ['confirm_password'],
  })

type Field = 'username' | 'email' | 'password' | 'confirm_password'

export function SetupForm() {
  const navigate = useNavigate()
  const [values, setValues] = useState({ username: '', email: '', password: '', confirm_password: '' })
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [globalError, setGlobalError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function set(field: Field) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setValues((v) => ({ ...v, [field]: e.target.value }))
      setErrors((err) => ({ ...err, [field]: undefined }))
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setGlobalError(null)

    const result = schema.safeParse(values)
    if (!result.success) {
      const fieldErrors: Partial<Record<Field, string>> = {}
      for (const issue of result.error.issues) {
        const field = issue.path[0] as Field
        if (!fieldErrors[field]) fieldErrors[field] = issue.message
      }
      setErrors(fieldErrors)
      return
    }

    setLoading(true)
    try {
      await setupApi.initAdmin({
        username: result.data.username,
        email: result.data.email,
        password: result.data.password,
      })
      // Connexion immédiate après création (cookie de session posé par le serveur).
      const user = await api.post<{ is_admin: boolean }>('/auth/login', {
        email: result.data.email,
        password: result.data.password,
      })
      setToken(user.is_admin)
      navigate('/')
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      if (status === 409) {
        // Compte déjà créé (race condition) → recharger pour afficher la page de login
        window.location.reload()
        return
      }
      setGlobalError('Une erreur est survenue. Veuillez réessayer.')
    } finally {
      setLoading(false)
    }
  }

  return (
    // Premier démarrage : même composition que la connexion, sans la colonne
    // éditoriale — il n'y a encore rien à présenter, il y a un compte à créer.
    <div className="flex min-h-screen items-center justify-center bg-paper">
      <div className="w-full max-w-[340px] px-6">
        <h3 className="mb-1">Bienvenue sur docflow</h3>
        <p className="mb-6 text-[13px] text-ink/[0.6]">
          Créez le compte administrateur pour commencer.
        </p>
        <form onSubmit={handleSubmit} className="grid gap-3.5">
          <Field label="Nom d'utilisateur" htmlFor="setup-username" error={errors.username}>
            <Input
              id="setup-username"
              value={values.username}
              onChange={set('username')}
              autoComplete="username"
              aria-invalid={errors.username ? 'true' : undefined}
              autoFocus
            />
          </Field>
          <Field label="Email" htmlFor="setup-email" error={errors.email}>
            <Input
              id="setup-email"
              type="email"
              value={values.email}
              onChange={set('email')}
              autoComplete="email"
              aria-invalid={errors.email ? 'true' : undefined}
            />
          </Field>
          <Field label="Mot de passe" htmlFor="setup-password" error={errors.password}>
            <Input
              id="setup-password"
              type="password"
              value={values.password}
              onChange={set('password')}
              autoComplete="new-password"
              aria-invalid={errors.password ? 'true' : undefined}
            />
          </Field>
          <Field
            label="Confirmer le mot de passe"
            htmlFor="setup-confirm"
            error={errors.confirm_password}
          >
            <Input
              id="setup-confirm"
              type="password"
              value={values.confirm_password}
              onChange={set('confirm_password')}
              autoComplete="new-password"
              aria-invalid={errors.confirm_password ? 'true' : undefined}
            />
          </Field>
          <div aria-live="polite" className="empty:hidden">
            {globalError && <p className="field-error">{globalError}</p>}
          </div>
          <Button type="submit" block disabled={loading}>
            {loading ? 'Création…' : 'Créer le compte administrateur'}
          </Button>
        </form>
      </div>
    </div>
  )
}
