import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../components/ui/button'
import { useToast } from '../components/Toast'
import { useOnboarding } from './useOnboarding'

/**
 * Parcours guidé à la première connexion (présentation du produit docflow).
 *
 * Monté dans l'AppLayout, il se pilote sur l'état serveur (useOnboarding).
 * Trois règles tenues par le rendu :
 * - **pause silencieuse** : la bulle ne s'affiche que sur la page de l'étape
 *   courante ; ailleurs, seuls les contrôles globaux restent (jamais de
 *   redirection forcée) ;
 * - **Fermer ≠ Suivant** : Fermer masque la bulle POUR CETTE SESSION, le
 *   parcours reprend à la même étape au prochain chargement ; Suivant avance
 *   l'index persisté ;
 * - **Rouvrir hors séquence** : hors de la bonne page, un message générique dit
 *   où aller, sans y emmener de force.
 */

// « Fermé pour cette session » : variable de MODULE, pas un state de composant.
// AppLayout est réinstancié à chaque navigation (chaque route l'enveloppe) : un
// state local se réinitialiserait à chaque changement de page. La variable de
// module survit aux navigations SPA et se remet à zéro au rechargement complet
// (F5 / reconnexion) — exactement ce que « Fermer » promet.
let fermeSession = false

export function OnboardingOverlay() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const { etapeCourante, surLaPage, index, total, actif, suivant, desactiver } = useOnboarding()
  const [, force] = useState(0)
  const rerender = () => force((n) => n + 1)

  if (!actif || !etapeCourante) return null

  const bulleVisible = surLaPage && !fermeSession

  function reouvrir() {
    fermeSession = false
    rerender()
    if (!surLaPage) {
      // Hors séquence : on ne redirige pas, on indique où aller.
      toast(
        t('onboarding.horsSequence', {
          page: t(`onboarding.steps.${etapeCourante!.key}.title`),
        }),
        'info',
      )
    }
  }

  function fermer() {
    fermeSession = true
    rerender()
  }

  if (!bulleVisible) {
    return (
      <div className="onboarding-controls">
        <Button size="sm" variant="secondary" onClick={reouvrir}>
          {t('onboarding.reouvrir')}
        </Button>
        <Button size="sm" variant="ghost" onClick={desactiver}>
          {t('onboarding.desactiver')}
        </Button>
      </div>
    )
  }

  const dernier = index + 1 >= total

  return (
    <div
      role="dialog"
      aria-label={t('onboarding.aria')}
      data-testid="onboarding-bulle"
      className="onboarding-bulle"
    >
      <p className="onboarding-progress">{t('onboarding.progression', { index: index + 1, total })}</p>
      <h3 className="onboarding-title">{t(`onboarding.steps.${etapeCourante.key}.title`)}</h3>
      <p className="onboarding-body">{t(`onboarding.steps.${etapeCourante.key}.body`)}</p>
      <div className="onboarding-actions">
        <div className="onboarding-actions-left">
          <Button size="sm" variant="ghost" onClick={fermer}>
            {t('onboarding.fermer')}
          </Button>
          <Button size="sm" variant="ghost" onClick={desactiver}>
            {t('onboarding.desactiver')}
          </Button>
        </div>
        <Button size="sm" onClick={suivant}>
          {dernier ? t('onboarding.terminer') : t('onboarding.suivant')}
        </Button>
      </div>
    </div>
  )
}
