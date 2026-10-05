import { type ButtonHTMLAttributes, forwardRef } from 'react'
import { clsx } from 'clsx'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** `danger` = magenta, réservé aux actions destructrices. */
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'icon'
  size?: 'sm' | 'md'
  /** Pleine largeur (formulaire d'authentification, colonne étroite). */
  block?: boolean
}

/** Bouton du système Broadsheet. Le style vit dans `styles/components.css` :
 *  ce composant ne fait qu'assembler les classes, jamais de valeur en dur. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', block = false, className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(
          'btn',
          variant === 'primary' && 'btn-primary',
          variant === 'secondary' && 'btn-secondary',
          variant === 'ghost' && 'btn-ghost',
          variant === 'danger' && 'btn-danger',
          variant === 'icon' && 'btn-icon btn-secondary',
          size === 'sm' && 'btn-sm',
          block && 'btn-block',
          className,
        )}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'
