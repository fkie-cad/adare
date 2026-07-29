import type { ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'

interface AsyncBoundaryProps {
  isPending: boolean
  isError: boolean
  error?: unknown
  onRetry: () => void
  /** Skeleton content shown while `isPending`. */
  loadingFallback: ReactNode
  isEmpty?: boolean
  emptyIcon?: LucideIcon
  emptyTitle?: string
  emptyDescription?: string
  errorFallbackMessage?: string
  children: ReactNode
}

/**
 * Shared loading/error/empty shell for list-style pages, replacing the
 * copy-pasted isPending/isError/empty blocks previously duplicated across
 * home.tsx, runs-list.tsx, experiments-list.tsx, projects-list.tsx, and
 * environments-list.tsx.
 */
export function AsyncBoundary({
  isPending,
  isError,
  error,
  onRetry,
  loadingFallback,
  isEmpty,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  errorFallbackMessage,
  children,
}: AsyncBoundaryProps) {
  if (isPending) {
    return <>{loadingFallback}</>
  }

  if (isError) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6 flex items-center gap-4">
          <p className="text-sm text-destructive flex-1">
            {(error as Error)?.message ?? errorFallbackMessage ?? 'Failed to load.'}
          </p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw size={14} />
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (isEmpty && emptyTitle) {
    return <EmptyState icon={emptyIcon} title={emptyTitle} description={emptyDescription} />
  }

  return <>{children}</>
}
