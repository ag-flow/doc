import { type ReactNode } from 'react'
import { clsx } from 'clsx'

/**
 * États transverses du système Broadsheet. Un seul jeu de primitives pour tous
 * les écrans : c'est la cohérence de ces états qui distingue une refonte d'un
 * simple thème.
 */

/** État vide : une phrase en sérif, une action, du blanc. Pas d'illustration,
 *  pas d'encadré — le vide fait partie du message. */
export function EmptyState({ message, action, className, testId }: {
  message: string
  action?: ReactNode
  className?: string
  testId?: string
}) {
  return (
    <div className={clsx('py-24 text-center', className)} data-testid={testId}>
      <p className="mb-5 text-[16px] text-ink/[0.6]">{message}</p>
      {action}
    </div>
  )
}

/** Bloc de squelette aux dimensions du contenu attendu. Jamais un spinner
 *  plein écran : la page doit garder sa forme pendant le chargement. */
export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <span
      aria-hidden="true"
      className={clsx('block animate-pulse rounded-sm bg-ink/[0.08]', className)}
      style={style}
    />
  )
}

/** Squelette de table : autant de lignes que la page en affichera, à la hauteur
 *  réelle d'une ligne — le contenu ne fait pas sauter la mise en page en arrivant. */
export function TableSkeleton({ rows = 6, columns = 4, testId = 'table-skeleton' }: {
  rows?: number
  columns?: number
  testId?: string
}) {
  return (
    <div role="status" aria-busy="true" data-testid={testId} className="mt-2">
      <span className="sr-only">Chargement…</span>
      {Array.from({ length: rows }, (_, r) => (
        <div
          key={r}
          className="flex items-center gap-5 border-b border-[var(--color-divider)] py-4"
        >
          {Array.from({ length: columns }, (_, c) => (
            <Skeleton
              key={c}
              className="h-4"
              // Largeurs décroissantes : la première colonne porte le libellé.
              style={{ flex: c === 0 ? '2 1 0' : '1 1 0', maxWidth: c === 0 ? 320 : 180 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

/** Squelette de feuille de document (lecture ou édition). */
export function SheetSkeleton({ testId = 'sheet-skeleton' }: { testId?: string }) {
  const widths = ['92%', '86%', '70%', '90%', '64%']
  return (
    <div role="status" aria-busy="true" data-testid={testId} className="space-y-3">
      <span className="sr-only">Chargement…</span>
      <Skeleton className="h-7" style={{ maxWidth: 360 }} />
      {widths.map((w, i) => (
        <Skeleton key={i} className="h-4" style={{ maxWidth: w }} />
      ))}
    </div>
  )
}

/** Erreur globale d'un écran : une ligne en magenta sous le titre de page.
 *  Les erreurs de champ ou de ligne restent au plus près de leur cause
 *  (`Field error`, cellule) — celle-ci ne sert qu'au niveau page. */
export function ErrorLine({ message, testId = 'error-line' }: {
  message: string | null | undefined
  testId?: string
}) {
  // La région existe en permanence : apparue en même temps que le message,
  // elle ne serait pas annoncée par les lecteurs d'écran.
  return (
    <div aria-live="polite" className="empty:hidden">
      {message && (
        <p className="mb-5 text-[14px] text-accent-2-700" data-testid={testId}>
          {message}
        </p>
      )}
    </div>
  )
}
