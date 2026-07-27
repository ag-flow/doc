import { type InputHTMLAttributes, forwardRef } from 'react'
import { clsx } from 'clsx'

type InputProps = InputHTMLAttributes<HTMLInputElement>

/** Champ du système Broadsheet (classe `.input` de `styles/components.css`). */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return <input ref={ref} className={clsx('input', className)} {...props} />
  },
)
Input.displayName = 'Input'
