import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { setupApi, setToken, api } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'

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
      // Connexion immédiate après création
      const res = await api.post<{ access_token: string }>('/auth/login', {
        email: result.data.email,
        password: result.data.password,
      })
      setToken(res.access_token)
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
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="mb-2 text-2xl font-semibold text-gray-900">Bienvenue sur docflow</h1>
        <p className="mb-6 text-sm text-gray-500">
          Créez le compte administrateur pour commencer.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Nom d'utilisateur
            </label>
            <Input
              value={values.username}
              onChange={set('username')}
              autoComplete="username"
              autoFocus
            />
            {errors.username && <p className="mt-1 text-xs text-red-600">{errors.username}</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Email</label>
            <Input
              type="email"
              value={values.email}
              onChange={set('email')}
              autoComplete="email"
            />
            {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email}</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Mot de passe</label>
            <Input
              type="password"
              value={values.password}
              onChange={set('password')}
              autoComplete="new-password"
            />
            {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password}</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Confirmer le mot de passe
            </label>
            <Input
              type="password"
              value={values.confirm_password}
              onChange={set('confirm_password')}
              autoComplete="new-password"
            />
            {errors.confirm_password && (
              <p className="mt-1 text-xs text-red-600">{errors.confirm_password}</p>
            )}
          </div>
          {globalError && <p className="text-sm text-red-600">{globalError}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Création…' : 'Créer le compte administrateur'}
          </Button>
        </form>
      </div>
    </div>
  )
}
