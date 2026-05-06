import clsx from 'clsx'

export default function Card({ className, as: Comp = 'div', children, ...rest }) {
  return (
    <Comp
      className={clsx(
        'bg-ink-900 border border-ink-800 rounded-xl',
        'shadow-[0_1px_0_0_rgba(255,255,255,0.04)_inset]',
        className,
      )}
      {...rest}
    >
      {children}
    </Comp>
  )
}

export function CardHeader({ className, children, ...rest }) {
  return (
    <div className={clsx('px-5 pt-5 pb-3', className)} {...rest}>
      {children}
    </div>
  )
}

export function CardBody({ className, children, ...rest }) {
  return (
    <div className={clsx('px-5 py-4', className)} {...rest}>
      {children}
    </div>
  )
}

export function CardFooter({ className, children, ...rest }) {
  return (
    <div
      className={clsx('px-5 py-3 border-t border-ink-800', className)}
      {...rest}
    >
      {children}
    </div>
  )
}
