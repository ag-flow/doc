import { type ButtonHTMLAttributes, forwardRef } from 'react'
import { clsx } from 'clsx'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger'
  size?: 'sm' | 'md'
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(
          'inline-flex items-center justify-center rounded font-medium transition-colors',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          size === 'sm' && 'px-2 py-1 text-sm',
          size === 'md' && 'px-4 py-2 text-sm',
          variant === 'primary' && 'bg-indigo-600 text-white hover:bg-indigo-700',
          variant === 'secondary' &&
            'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50',
          variant === 'danger' && 'bg-red-600 text-white hover:bg-red-700',
          className,
        )}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'
