import { LoaderCircle } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const base =
  'group relative inline-flex h-10 select-none items-center justify-center gap-2 overflow-hidden rounded-md px-4 text-[15px] font-medium ' +
  'transition-[background,color,box-shadow,border-color,transform,filter] duration-[420ms] ease-[var(--ease-soft)] ' +
  'active:translate-y-0 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 ' +
  // иконка слегка «оживает» при наведении: стрелки сдвигаются, остальные чуть увеличиваются
  '[&_svg]:transition-transform [&_svg]:duration-500 [&_svg]:ease-[var(--ease-soft)] hover:[&_svg]:scale-110'

const variants: Record<Variant, string> = {
  // главная: подъём, усиленное свечение и пробегающий блик (.btn-shine в index.css)
  primary: 'btn-shine bg-accent text-accent-ink glow-accent hover:-translate-y-px hover:brightness-110 hover:shadow-[0_0_0_1px_var(--accent-soft),0_14px_40px_-12px_var(--accent-glow)]',
  secondary:
    'border border-line-strong bg-surface-2/60 text-text hover:-translate-y-px hover:border-accent/60 hover:text-accent hover:shadow-[0_8px_24px_-14px_var(--accent-glow)]',
  ghost: 'text-muted hover:bg-surface-2 hover:text-text',
  danger: 'bg-danger-soft text-danger hover:-translate-y-px hover:bg-danger/20 hover:shadow-[0_8px_24px_-14px_var(--danger)]',
}

export function buttonClass(variant: Variant = 'primary', extra = '') {
  return `${base} ${variants[variant]} ${extra}`
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  loading?: boolean
  loadingText?: string
  icon?: ReactNode
}

export function Button({ variant = 'primary', loading, loadingText, icon, children, className = '', disabled, ...rest }: ButtonProps) {
  return (
    <button className={buttonClass(variant, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : icon}
      {loading && loadingText ? loadingText : children}
    </button>
  )
}

export function ButtonLink({ variant = 'primary', className = '', icon, children, ...rest }: LinkProps & { variant?: Variant; icon?: ReactNode }) {
  return (
    <Link className={buttonClass(variant, className)} {...rest}>
      {icon}
      {children}
    </Link>
  )
}
