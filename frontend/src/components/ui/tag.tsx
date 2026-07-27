import { type ReactNode } from 'react'
import { clsx } from 'clsx'

interface TagProps {
  /** `accent-2` = magenta : échec, rejet, alerte. Jamais décoratif. */
  variant?: 'accent' | 'accent-2' | 'neutral' | 'outline'
  className?: string
  children: ReactNode
}

/** Étiquette du système Broadsheet (classe `.tag`). */
export function Tag({ variant = 'neutral', className, children }: TagProps) {
  return (
    <span
      className={clsx(
        'tag',
        variant === 'accent' && 'tag-accent',
        variant === 'accent-2' && 'tag-accent-2',
        variant === 'neutral' && 'tag-neutral',
        variant === 'outline' && 'tag-outline',
        className,
      )}
    >
      {children}
    </span>
  )
}
