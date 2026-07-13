import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { setToken } from '../lib/api'
import { completeOidcCallback } from '../lib/oidcClient'

/** Page de retour du flow OIDC : vérifie le state, échange le code via le
 *  backend, stocke le JWT docflow puis redirige vers l'accueil. */
export function OidcCallback() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [pendingValidation, setPendingValidation] = useState(false)
  // Le code d'autorisation est à usage unique : ne jamais le poster deux fois
  // (double-montage StrictMode en dev).
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    const params = new URLSearchParams(window.location.search)
    completeOidcCallback(params)
      .then((token) => {
        setToken(token)
        navigate('/', { replace: true })
      })
      .catch((err: unknown) => {
        const detail = (err as { detail?: unknown }).detail
        if (detail === 'PendingValidation') setPendingValidation(true)
        else setError(t('login.oidcError'))
      })
  }, [navigate, t])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="mb-6 text-2xl font-semibold text-gray-900">{t('login.title')}</h1>
        {!error && !pendingValidation && (
          <p className="text-sm text-gray-600" data-testid="oidc-progress">
            {t('login.oidcLoading')}
          </p>
        )}
        {error && (
          <p className="text-sm text-red-600" data-testid="oidc-error">
            {error}
          </p>
        )}
        {pendingValidation && (
          <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {t('login.pendingValidation')}
          </div>
        )}
        {(error || pendingValidation) && (
          <Link
            to="/login"
            className="mt-4 block text-sm text-indigo-600 hover:underline"
            data-testid="back-to-login"
          >
            {t('login.backToLogin')}
          </Link>
        )}
      </div>
    </div>
  )
}
