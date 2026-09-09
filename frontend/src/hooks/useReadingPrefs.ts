import { useCallback, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { prefsApi } from '../lib/api'

/**
 * Préférences de lecture d'un document, communes aux trois réglages de lecture
 * (repli du sommaire, repli des propriétés, échelle typographique). Un magasin
 * UNIQUE plutôt que trois mécanismes ad hoc : ce sont toutes des préférences de
 * lecture par utilisateur, elles suivent le compte (prefsApi), pas le navigateur.
 *
 * Le cache localStorage sert au premier rendu (paint instantané, repli hors
 * ligne) ; `useQuery` déduplique l'appel réseau entre la vue lecture et la page
 * éditeur qui montent toutes deux ce hook.
 */

/** Paliers d'échelle (multiplicateurs), de 30 % à 300 %. Bornés, pas un curseur
 *  continu : la mise en page reste cohérente à chaque cran. 1 = échelle par défaut. */
export const READING_SCALE_STEPS = [
  0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2, 2.5, 3,
] as const
export const DEFAULT_SCALE_STEP = 6

const PREF_KEY = 'reading-prefs'
const CACHE_KEY = 'docflow.reading-prefs'
/** Ancienne clé du seul toggle sommaire — reprise comme défaut tant qu'aucune
 *  préférence de lecture unifiée n'a encore été enregistrée. */
const LEGACY_TOC_KEY = 'docflow.doc.toc'
const QUERY_KEY = ['reading-prefs'] as const

export interface ReadingPrefs {
  tocOpen: boolean
  propsOpen: boolean
  scaleStep: number
}

function clampStep(n: number): number {
  if (!Number.isFinite(n)) return DEFAULT_SCALE_STEP
  return Math.min(READING_SCALE_STEPS.length - 1, Math.max(0, Math.round(n)))
}

function defaults(): ReadingPrefs {
  const legacyToc = localStorage.getItem(LEGACY_TOC_KEY)
  return {
    tocOpen: legacyToc !== '0',
    propsOpen: true,
    scaleStep: DEFAULT_SCALE_STEP,
  }
}

/** Tolère une valeur partielle ou corrompue (schéma qui évolue, écriture
 *  concurrente) : chaque champ retombe sur le défaut plutôt que de casser. */
function normalize(value: Partial<ReadingPrefs> | null | undefined): ReadingPrefs {
  const base = defaults()
  if (!value || typeof value !== 'object') return base
  return {
    tocOpen: typeof value.tocOpen === 'boolean' ? value.tocOpen : base.tocOpen,
    propsOpen: typeof value.propsOpen === 'boolean' ? value.propsOpen : base.propsOpen,
    scaleStep: clampStep(typeof value.scaleStep === 'number' ? value.scaleStep : base.scaleStep),
  }
}

function readCache(): ReadingPrefs {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return normalize(raw ? (JSON.parse(raw) as Partial<ReadingPrefs>) : null)
  } catch {
    return defaults()
  }
}

function writeCache(prefs: ReadingPrefs): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(prefs))
  } catch {
    /* quota plein / stockage refusé : la persistance compte prend le relais */
  }
}

export interface UseReadingPrefs extends ReadingPrefs {
  scale: number
  /** Vrai quand sommaire ET propriétés sont repliés (mode lecture immersif). */
  readingMode: boolean
  toggleToc: () => void
  toggleProps: () => void
  setReadingMode: (on: boolean) => void
  incScale: () => void
  decScale: () => void
  resetScale: () => void
  canInc: boolean
  canDec: boolean
}

export function useReadingPrefs(): UseReadingPrefs {
  const qc = useQueryClient()
  // Passe à vrai dès la première interaction : la réconciliation avec la valeur
  // compte (GET) ne doit JAMAIS écraser un changement déjà fait par l'utilisateur.
  const touched = useRef(false)

  // Le cache local (initialData) est la source fraîche : `staleTime: Infinity`
  // interdit tout refetch automatique qui, en vol, écraserait une mise à jour
  // optimiste. La valeur compte est réconciliée une seule fois ci-dessous.
  const { data } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: async () => normalize((await prefsApi.get<ReadingPrefs>(PREF_KEY)).value),
    initialData: readCache,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  const prefs = data

  // Réconciliation cross-device : on lit la valeur compte au montage et on
  // l'applique tant que l'utilisateur n'a rien changé et qu'une valeur existe.
  useEffect(() => {
    let cancelled = false
    prefsApi
      .get<ReadingPrefs>(PREF_KEY)
      .then(({ value }) => {
        if (cancelled || touched.current || !value) return
        qc.setQueryData(QUERY_KEY, normalize(value))
      })
      .catch(() => {
        /* hors ligne : le cache local fait foi */
      })
    return () => {
      cancelled = true
    }
  }, [qc])

  // Le patch peut être une fonction de l'état COURANT (lu dans le cache, pas
  // dans une capture de rendu) : des clics rapides (échelle) s'accumulent sans
  // dépendre d'un re-render entre deux appels.
  const update = useCallback(
    (patch: Partial<ReadingPrefs> | ((cur: ReadingPrefs) => Partial<ReadingPrefs>)) => {
      touched.current = true
      const current = normalize(qc.getQueryData<ReadingPrefs>(QUERY_KEY) ?? readCache())
      const resolved = typeof patch === 'function' ? patch(current) : patch
      const next = normalize({ ...current, ...resolved })
      qc.setQueryData(QUERY_KEY, next) // application immédiate (optimiste)
      void prefsApi.set(PREF_KEY, next) // persistance compte, best-effort
    },
    [qc],
  )

  // La valeur (compte ou cache) est recopiée dans le cache localStorage à chaque
  // changement : le prochain chargement repart de l'état le plus récent connu.
  useEffect(() => {
    writeCache(prefs)
  }, [prefs])

  const scale = READING_SCALE_STEPS[prefs.scaleStep]

  // L'échelle est portée par une variable CSS de racine (`--reading-scale`)
  // consommée par les tokens typographiques de la feuille — et NON par un
  // `transform: scale()` : un transform casse le positionnement collant du
  // sommaire et de l'en-tête, rend le texte flou, fausse les zones de clic et
  // n'apporte aucun reflux (exactement ce dont on a besoin sur petit écran).
  // Elle reste posée sur :root car c'est un réglage global : il vaut aussi en
  // édition, sans dépendre du montage de la vue lecture.
  useEffect(() => {
    document.documentElement.style.setProperty('--reading-scale', String(scale))
  }, [scale])

  return {
    ...prefs,
    scale,
    readingMode: !prefs.tocOpen && !prefs.propsOpen,
    toggleToc: () => update((c) => ({ tocOpen: !c.tocOpen })),
    toggleProps: () => update((c) => ({ propsOpen: !c.propsOpen })),
    setReadingMode: (on: boolean) => update({ tocOpen: !on, propsOpen: !on }),
    incScale: () => update((c) => ({ scaleStep: clampStep(c.scaleStep + 1) })),
    decScale: () => update((c) => ({ scaleStep: clampStep(c.scaleStep - 1) })),
    resetScale: () => update({ scaleStep: DEFAULT_SCALE_STEP }),
    canInc: prefs.scaleStep < READING_SCALE_STEPS.length - 1,
    canDec: prefs.scaleStep > 0,
  }
}
