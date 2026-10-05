import { type ReactNode } from 'react'
import { clsx } from 'clsx'

interface FieldProps {
  label: string
  htmlFor?: string
  /** Aide sous le champ. Masquée quand une erreur est affichée. */
  hint?: string
  error?: string | null
  className?: string
  children: ReactNode
}

/** Groupe libellé + champ + aide/erreur. Le message d'erreur porte le magenta ;
 *  c'est le seul emploi de la seconde couleur dans un formulaire. */
export function Field({ label, htmlFor, hint, error, className, children }: FieldProps) {
  return (
    <div className={clsx('field', className)}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? (
        <p className="field-error" role="alert">{error}</p>
      ) : hint ? (
        <p className="field-hint">{hint}</p>
      ) : null}
    </div>
  )
}
