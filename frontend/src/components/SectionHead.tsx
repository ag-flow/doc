import { type ReactNode } from 'react'

/**
 * Tête de section Broadsheet : surtitre cyan, filet court cyan prolongé par un
 * filet fin, puis le titre et ses actions sur la même ligne de base. Elle
 * remplace tout bandeau de page — c'est le seul cadre admis en tête d'écran.
 */
export function SectionHead({ kicker, title, children }: {
  kicker: string
  title: string
  /** Actions et filtres, alignés à droite sur la ligne du titre. */
  children?: ReactNode
}) {
  return (
    <>
      <div className="text-[11px] font-[600] uppercase tracking-[0.09em] text-accent-700">
        {kicker}
      </div>
      <div className="mt-2.5 flex items-center">
        <div className="h-0.5 w-11 bg-accent" />
        <div className="h-px flex-1 bg-[var(--color-divider)]" />
      </div>
      <div className="mt-3.5 mb-4 flex flex-wrap items-end gap-5">
        <h1 className="m-0 text-[46px] tracking-[-0.03em]">{title}</h1>
        <span className="flex-1" />
        {children}
      </div>
    </>
  )
}
