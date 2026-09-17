import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { prefsApi } from '../lib/api'
import { ONBOARDING_PREF_KEY, ONBOARDING_STEPS, type OnboardingStep } from './steps'

/**
 * État du parcours guidé, dérivé de la préférence serveur `onboarding`.
 *
 * La progression est un simple index d'étape (`step`) ; `disabled` l'arrête
 * définitivement. Une seule clé de préférence porte les deux (le backend range
 * n'importe quel JSON par clé) → une query, une écriture.
 *
 * Ce hook ne connaît PAS l'état « bulle fermée pour cette session » : c'est de
 * l'affichage local, porté par l'overlay. Ici vit ce qui survit d'une connexion
 * à l'autre — l'index et le drapeau désactivé.
 */
export interface OnboardingPrefs {
  step: number
  disabled: boolean
}

const DEFAULT_PREFS: OnboardingPrefs = { step: 0, disabled: false }
const QUERY_KEY = ['onboarding'] as const

export interface OnboardingState {
  /** Étape courante quelle que soit la page (null si parcours fini/désactivé). */
  etapeCourante: OnboardingStep | null
  /** Vrai si l'utilisateur est sur la page de l'étape courante. */
  surLaPage: boolean
  index: number
  total: number
  actif: boolean
  /** « Suivant » : passe à l'étape suivante. */
  suivant: () => void
  /** « Désactiver » : arrêt définitif. */
  desactiver: () => void
}

export function useOnboarding(): OnboardingState {
  const qc = useQueryClient()
  const location = useLocation()

  const { data } = useQuery<OnboardingPrefs>({
    queryKey: QUERY_KEY,
    queryFn: async () =>
      (await prefsApi.get<OnboardingPrefs>(ONBOARDING_PREF_KEY)).value ?? DEFAULT_PREFS,
    staleTime: Infinity,
  })
  const prefs = data ?? DEFAULT_PREFS

  // Écriture optimiste + rollback : la bulle réagit tout de suite, la
  // persistance suit ; un échec réseau ne fige pas une progression fausse.
  const write = useMutation({
    mutationFn: (next: OnboardingPrefs) => prefsApi.set(ONBOARDING_PREF_KEY, next),
    onMutate: async (next: OnboardingPrefs) => {
      await qc.cancelQueries({ queryKey: QUERY_KEY })
      const prev = qc.getQueryData<OnboardingPrefs>(QUERY_KEY)
      qc.setQueryData<OnboardingPrefs>(QUERY_KEY, next)
      return { prev }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(QUERY_KEY, ctx.prev)
    },
  })

  const index = prefs.step
  const actif = !prefs.disabled && index < ONBOARDING_STEPS.length
  const etapeCourante = actif ? ONBOARDING_STEPS[index] : null

  return {
    etapeCourante,
    surLaPage: etapeCourante !== null && location.pathname === etapeCourante.path,
    index,
    total: ONBOARDING_STEPS.length,
    actif,
    suivant: () => write.mutate({ ...prefs, step: index + 1 }),
    desactiver: () => write.mutate({ ...prefs, disabled: true }),
  }
}
