import * as React from 'react'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { useToastStore, type Toast as ToastItem, type ToastKind } from '@/stores/toast-store'
import { cn } from '@/lib/utils'

const DEFAULT_TTL_MS = 4000

const kindStyles: Record<ToastKind, { icon: React.ComponentType<{ className?: string }>; accent: string }> = {
  success: { icon: CheckCircle2, accent: 'text-green-500' },
  error: { icon: XCircle, accent: 'text-destructive' },
  info: { icon: Info, accent: 'text-blue-500' },
}

function ToastCard({ toast }: { toast: ToastItem }) {
  const dismiss = useToastStore((s) => s.dismiss)
  const ttl = toast.ttlMs ?? DEFAULT_TTL_MS
  const { icon: Icon, accent } = kindStyles[toast.kind]

  React.useEffect(() => {
    if (ttl <= 0) return
    const h = window.setTimeout(() => dismiss(toast.id), ttl)
    return () => window.clearTimeout(h)
  }, [toast.id, ttl, dismiss])

  return (
    <div
      role="status"
      className={cn(
        'pointer-events-auto flex min-w-[280px] max-w-md items-start gap-3 rounded-md border border-border bg-background p-3 shadow-lg',
      )}
    >
      <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', accent)} />
      <div className="flex-1">
        <div className="text-sm font-medium">{toast.title}</div>
        {toast.description && (
          <div className="mt-0.5 text-xs text-muted-foreground">{toast.description}</div>
        )}
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        className="rounded-sm text-muted-foreground hover:text-foreground"
        onClick={() => dismiss(toast.id)}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

export function ToastViewport() {
  const toasts = useToastStore((s) => s.toasts)
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} />
      ))}
    </div>
  )
}

function push(kind: ToastKind, title: string, description?: string) {
  return useToastStore.getState().push({ kind, title, description })
}

export const toast = {
  success: (title: string, description?: string) => push('success', title, description),
  error: (title: string, description?: string) => push('error', title, description),
  info: (title: string, description?: string) => push('info', title, description),
}
