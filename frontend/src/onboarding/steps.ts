/**
 * Séquence du parcours guidé docflow — présentation du produit.
 *
 * Séquence INDÉPENDANTE de celle des autres modules (devpod…) : progression
 * propre à docflow, persistée par utilisateur (préférence `onboarding`).
 *
 * Chaque étape est ancrée sur une route STABLE du portail (pas de segment
 * dynamique) : la bulle ne s'affiche que lorsque `location.pathname` vaut
 * exactement ce `path`. Les concepts vivant sous `/ws/:slug/...` (blocs,
 * documents, éditeur, types) n'ont pas de route fixe : ils sont présentés dans
 * le texte de l'étape d'accueil plutôt qu'ancrés sur une page changeante.
 *
 * Le contenu des messages vit dans les clés i18n `onboarding.steps.<key>` —
 * relisable et ajustable sans toucher au code.
 */

export interface OnboardingStep {
  /** Clé i18n : `onboarding.steps.<key>.title` / `.body`. */
  key: string
  /** Route stable où l'étape a un sens. La bulle ne s'affiche que là. */
  path: string
}

/** Séquence plate, dans l'ordre de présentation. */
export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  { key: 'bienvenue', path: '/workspaces' },
  { key: 'templates', path: '/templates' },
  { key: 'automations', path: '/automations' },
  { key: 'contracts', path: '/contracts' },
  { key: 'apiKeys', path: '/api-keys' },
  { key: 'profil', path: '/me' },
] as const

/** Clé de préférence serveur (valeur = `{ step, disabled }`). */
export const ONBOARDING_PREF_KEY = 'onboarding'
