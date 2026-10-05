import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'

interface FullscreenOverlayProps {
  /** Libellé accessible du dialogue (nom du rendu affiché). */
  label: string
  onClose: () => void
  children: ReactNode
}

/**
 * Vue plein écran d'un rendu (diagramme, maquette, image d'artefact). Overlay
 * unique porté par la couche de rendu commune plutôt que réimplémenté par chaque
 * codec : occupe toute la fenêtre sur fond neutre, se ferme par Échap, par le
 * bouton, ou par un clic hors du rendu, et rend le focus à l'élément d'origine.
 *
 * Le contenu est rendu à sa taille naturelle maximale sans déformation ; un SVG
 * reste net (pas de bitmap étiré). L'appelant fournit le rendu à afficher.
 */
export function FullscreenOverlay({ label, onClose, children }: FullscreenOverlayProps) {
  const { t } = useTranslation()
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    // Élément déclencheur (encore focalisé au montage) : on lui rend le focus à
    // la fermeture — exigence d'accessibilité de la fiche.
    const opener = document.activeElement as HTMLElement | null

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    closeRef.current?.focus()

    // Verrou du défilement de fond tant que l'overlay est ouvert.
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      opener?.focus?.()
    }
  }, [onClose])

  return createPortal(
    <div
      className="df-fullscreen"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      // Clic sur le fond (et non sur le rendu) = fermeture.
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <button
        ref={closeRef}
        type="button"
        className="df-fullscreen-close"
        onClick={onClose}
        title={t('reading.fullscreenClose')}
        aria-label={t('reading.fullscreenClose')}
        data-testid="fullscreen-close"
      >
        <X size={20} weight="bold" />
      </button>
      <div className="df-fullscreen-body">{children}</div>
    </div>,
    document.body,
  )
}
