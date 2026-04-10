import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        destructive: 'border-transparent bg-destructive/15 text-destructive',
        outline: 'text-foreground',
        success: 'border-transparent bg-green-500/15 text-green-700 dark:text-green-400',
        warning: 'border-transparent bg-yellow-500/15 text-yellow-700 dark:text-yellow-400',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
)
Badge.displayName = 'Badge'

function statusToVariant(status: string | null | undefined): BadgeVariant {
  if (!status) return 'outline'
  const s = status.toLowerCase()
  if (['pending', 'queued', 'waiting'].includes(s)) return 'secondary'
  if (['running', 'in_progress', 'active'].includes(s)) return 'default'
  if (['success', 'passed', 'completed', 'ok', 'done'].includes(s)) return 'success'
  if (['failed', 'error', 'errored'].includes(s)) return 'destructive'
  if (['cancelled', 'canceled', 'aborted', 'timeout', 'skipped'].includes(s)) return 'warning'
  return 'outline'
}

export { Badge, badgeVariants, statusToVariant, type BadgeVariant }
