import clsx from 'clsx'
import { forwardRef } from 'react'

const Input = forwardRef(function Input(
  { className, label, hint, error, id, type = 'text', ...rest },
  ref,
) {
  const inputId = id || rest.name
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-medium text-ink-200 tracking-wide uppercase"
        >
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        type={type}
        className={clsx(
          'w-full h-10 px-3 rounded-lg bg-ink-900 text-ink-100',
          'border border-ink-700 placeholder:text-ink-400',
          'transition-colors duration-150',
          'hover:border-ink-600',
          'focus:outline-none focus:border-kerf-300 focus:ring-4 focus:ring-kerf-300/20',
          error && 'border-red-500/70 focus:border-red-500 focus:ring-red-500/20',
          className,
        )}
        {...rest}
      />
      {hint && !error && <p className="text-xs text-ink-400">{hint}</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
})

export default Input

export const Textarea = forwardRef(function Textarea(
  { className, label, hint, error, id, rows = 3, ...rest },
  ref,
) {
  const inputId = id || rest.name
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-medium text-ink-200 tracking-wide uppercase"
        >
          {label}
        </label>
      )}
      <textarea
        ref={ref}
        id={inputId}
        rows={rows}
        className={clsx(
          'w-full px-3 py-2 rounded-lg bg-ink-900 text-ink-100 resize-none',
          'border border-ink-700 placeholder:text-ink-400',
          'transition-colors duration-150',
          'hover:border-ink-600',
          'focus:outline-none focus:border-kerf-300 focus:ring-4 focus:ring-kerf-300/20',
          error && 'border-red-500/70 focus:border-red-500 focus:ring-red-500/20',
          className,
        )}
        {...rest}
      />
      {hint && !error && <p className="text-xs text-ink-400">{hint}</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
})
