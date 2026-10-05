import { type ReactNode } from 'react'
import { HeaderActions } from './HeaderSlot'

interface Props {
  /** Surtitre cyan : type fonctionnel · bloc. */
  kicker: string
  /** Titre : texte en lecture, champ de saisie en édition. */
  title: ReactNode
  /** Ligne méta sous le titre (slug, version, statut). */
  meta?: ReactNode
  /** Barre d'actions — montée dans l'EN-TÊTE, sur la ligne du fil d'Ariane. */
  actions?: ReactNode
  /** Colonne de droite (propriétés, backlinks). Absente = colonne unique. */
  aside?: ReactNode
  /** Colonne de gauche (sommaire du bloc). Absente = pas de colonne. */
  nav?: ReactNode
  /** Contenu de la feuille (texte du document). */
  children: ReactNode
  /** Sous la feuille, pleine mesure : enfants, réactions, commentaires. */
  footer?: ReactNode
  /** La feuille porte une surface NON textuelle (diagramme, grille de champs).
   *
   *  La mesure de lecture (~72ch) et les marges de la feuille sont calibrées
   *  pour du texte : appliquées à un plan de travail, elles l'enferment dans une
   *  colonne étroite. Une surface qui n'est pas de la prose le déclare ici. */
  wide?: boolean
  /** Rédaction plein écran : calque, barre minimale, pas de colonnes.
   *
   *  Ce mode vivait AILLEURS, dans une branche de `DocumentEditor` qui
   *  court-circuitait cette coquille. Il avait déjà dérivé : il codait
   *  `wiki-prose` en dur et ignorait donc `wide`. Le rapatrier ici garantit que
   *  la classe de la feuille est calculée à UN SEUL endroit, pour les trois
   *  modes — c'est la seule façon d'empêcher la divergence de revenir. */
  focus?: boolean
  /** Barre du mode focus : titre lu, statut, enregistrer, sortir. */
  focusBar?: ReactNode
}

/**
 * Ossature de l'écran document, partagée par la lecture ET l'édition : mêmes
 * marges, même mesure, même feuille. C'est ce partage qui garantit que passer
 * de l'une à l'autre ne déplace pas le texte d'un pixel — deux implémentations
 * parallèles dériveraient au premier ajustement.
 */
export function DocumentShell({
  kicker,
  title,
  meta,
  actions,
  aside,
  nav,
  children,
  footer,
  wide,
  focus,
  focusBar,
}: Props) {
  // UN seul calcul de la classe de feuille, partagé par les trois modes.
  const sheetClass = `doc-sheet${wide ? ' doc-sheet-wide' : ' wiki-prose'}`

  if (focus) {
    return (
      <div className="fixed inset-0 z-40 overflow-y-auto bg-paper">
        <div className="sticky top-0 z-10 flex items-center gap-3 bg-paper px-[30px] py-3.5">
          {focusBar}
        </div>
        <div className={`mx-auto px-6 pb-32 ${wide ? 'max-w-none' : 'max-w-[820px]'}`}>
          <div className={sheetClass} data-testid="focus-sheet">{children}</div>
        </div>
      </div>
    )
  }

  return (
    <div className={`doc-shell${nav ? ' doc-shell-nav' : ''}${aside ? ' doc-shell-aside' : ''}`}>
      {actions && <HeaderActions>{actions}</HeaderActions>}
      <div className="mb-1.5">
        <div className="text-[11px] font-[600] uppercase tracking-[0.09em] text-accent-700">
          {kicker}
        </div>
        <div className="mt-3">{title}</div>
      </div>

      {meta && <div className="doc-meta">{meta}</div>}

      <div className={`doc-grid${aside ? ' doc-grid-aside' : ''}${nav ? ' doc-grid-nav' : ''}`}>
        {nav && <div className="doc-nav-col">{nav}</div>}
        <div className="min-w-0">
          <div className={sheetClass}>{children}</div>
          {footer}
        </div>
        {aside && <aside className="doc-aside">{aside}</aside>}
      </div>
    </div>
  )
}
