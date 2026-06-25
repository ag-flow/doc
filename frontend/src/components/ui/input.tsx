import { type InputHTMLAttributes, forwardRef } from 'react'
import { clsx } from 'clsx'

type InputProps = InputHTMLAttributes<HTMLInputElement>

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={clsx(
          'block w-full rounded border border-gray-300 px-3 py-2 text-sm',
          'placeholder:text-gray-400',
          'focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500',
          'disabled:bg-gray-100 disabled:cursor-not-allowed',
          className,
        )}
        {...props}
      />
    )
  },
)
Input.displayName = 'Input'
