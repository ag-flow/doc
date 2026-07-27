import { type ReactNode } from 'react'

interface Props {
  /** Surtitre cyan : type fonctionnel · bloc. */
  kicker: string
  /** Titre : texte en lecture, champ de saisie en édition. */
  title: ReactNode
  /** Ligne méta sous le titre (slug, version, statut). */
  meta?: ReactNode
  /** Barre d'actions, alignée en haut à droite du contenu. */
  actions?: ReactNode
  /** Colonne de droite (propriétés, backlinks). Absente = colonne unique. */
  aside?: ReactNode
  /** Contenu de la feuille (texte du document). */
  children: ReactNode
  /** Sous la feuille, pleine mesure : enfants, réactions, commentaires. */
  footer?: ReactNode
}

/**
 * Ossature de l'écran document, partagée par la lecture ET l'édition : mêmes
 * marges, même mesure, même feuille. C'est ce partage qui garantit que passer
 * de l'une à l'autre ne déplace pas le texte d'un pixel — deux implémentations
 * parallèles dériveraient au premier ajustement.
 */
export function DocumentShell({ kicker, title, meta, actions, aside, children, footer }: Props) {
  return (
    <div className="mx-auto max-w-[1440px] px-[30px] pt-12 pb-24">
      <div className="mb-1.5 flex items-start gap-5">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-[600] uppercase tracking-[0.09em] text-accent-700">
            {kicker}
          </div>
          <div className="mt-3">{title}</div>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-1.5 pt-2">{actions}</div>}
      </div>

      {meta && <div className="doc-meta">{meta}</div>}

      <div className={`doc-grid${aside ? ' doc-grid-aside' : ''}`}>
        <div className="min-w-0">
          <div className="doc-sheet wiki-prose">{children}</div>
          {footer}
        </div>
        {aside && <aside className="doc-aside">{aside}</aside>}
      </div>
    </div>
  )
}
