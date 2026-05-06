import clsx from 'clsx'

const VARIANTS = {
  primary:
    'bg-kerf-300 text-ink-950 hover:bg-kerf-200 active:bg-kerf-400 ' +
    'shadow-[0_1px_0_0_rgba(255,255,255,0.18)_inset,0_1px_2px_rgba(0,0,0,0.5)] ' +
    'disabled:bg-kerf-700 disabled:text-ink-300',
  secondary:
    'bg-ink-700 text-ink-100 hover:bg-ink-600 active:bg-ink-700 ' +
    'border border-ink-600 disabled:bg-ink-800 disabled:text-ink-400',
  ghost:
    'bg-transparent text-ink-100 hover:bg-ink-800/80 active:bg-ink-800 ' +
    'disabled:text-ink-400',
  outline:
    'bg-transparent text-ink-100 border border-ink-600 hover:bg-ink-800/60 hover:border-ink-500 ' +
    'disabled:text-ink-400 disabled:border-ink-700',
  danger:
    'bg-red-500/90 text-white hover:bg-red-500 active:bg-red-600 ' +
    'disabled:bg-red-900 disabled:text-ink-300',
}

const SIZES = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-md',
  md: 'h-10 px-4 text-sm gap-2 rounded-lg',
  lg: 'h-12 px-6 text-base gap-2 rounded-lg',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  className,
  type = 'button',
  as: Comp = 'button',
  children,
  ...rest
}) {
  return (
    <Comp
      type={Comp === 'button' ? type : undefined}
      className={clsx(
        'inline-flex items-center justify-center font-medium tracking-tight',
        'transition-colors duration-150 select-none',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950',
        'disabled:cursor-not-allowed',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {children}
    </Comp>
  )
}
