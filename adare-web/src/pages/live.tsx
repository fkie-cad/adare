import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { Activity, FileText, Monitor, PanelsTopLeft } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { VmLiveView } from '@/components/vm/vm-live-view'
import { VmLogTail } from '@/components/vm/vm-log-tail'
import { useRunningVmInstances, type VmInstance } from '@/api/hooks/use-vms'
import { cn } from '@/lib/utils'

export type LiveViewMode = 'both' | 'display' | 'logs'

const MODES: { value: LiveViewMode; label: string; icon: typeof Monitor }[] = [
  { value: 'both', label: 'Both', icon: PanelsTopLeft },
  { value: 'display', label: 'Display', icon: Monitor },
  { value: 'logs', label: 'Logs', icon: FileText },
]

function InstanceListItem({
  instance,
  selected,
  onSelect,
}: {
  instance: VmInstance
  selected: boolean
  onSelect: () => void
}) {
  const name = String(instance.instance_name ?? instance.id)
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          'w-full rounded-md border px-3 py-2 text-left transition-colors',
          selected ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50',
        )}
      >
        <div className="flex items-center gap-2">
          <Badge variant={statusToVariant(instance.status ?? null)}>{instance.status ?? '—'}</Badge>
          <span className="truncate font-mono text-xs" title={name}>
            {name}
          </span>
        </div>
        <div className="mt-1 truncate text-xs text-muted-foreground">
          {instance.vm_name ?? '—'}
          {instance.hypervisor ? ` · ${instance.hypervisor}` : ''}
        </div>
      </button>
    </li>
  )
}

function SelectedInstance({ instance, mode }: { instance: VmInstance; mode: LiveViewMode }) {
  const name = String(instance.instance_name ?? instance.id)
  const runId = instance.current_experiment_run_id
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{instance.vm_name ?? name}</span>
        <span className="font-mono text-xs text-muted-foreground">{name}</span>
        {runId && (
          <Link
            to="/runs/$ulid"
            params={{ ulid: runId }}
            className="font-mono text-xs text-primary hover:underline"
            title="Open the run this instance belongs to"
          >
            run {runId}
          </Link>
        )}
      </div>
      {mode !== 'logs' && (
        <div
          className={cn(
            'overflow-hidden rounded-md border border-border',
            mode === 'both' ? 'h-[55%] min-h-[240px] shrink-0' : 'min-h-0 flex-1',
          )}
        >
          {/* key: a new instance gets a fresh viewer connection. View-only: no input reaches the guest. */}
          <VmLiveView key={name} vmName={name} viewOnly className="h-full" />
        </div>
      )}
      {mode !== 'display' && (
        <div className="min-h-[200px] flex-1 overflow-hidden rounded-md border border-border">
          <VmLogTail key={instance.id} instanceId={String(instance.id)} className="h-full" />
        </div>
      )}
    </div>
  )
}

/**
 * Running VMs at a glance: pick a running instance and watch its display (view
 * only, no input reaches the guest) and/or follow its logs live.
 */
export default function LivePage() {
  const { instance: selectedId, mode = 'both' } = useSearch({ from: '/live' })
  const navigate = useNavigate({ from: '/live' })
  const { data, isPending, isError, error, refetch } = useRunningVmInstances()

  const instances = data ?? []
  const selected = instances.find((i) => String(i.id) === selectedId) ?? instances[0]

  const select = (id: string) => navigate({ search: (prev) => ({ ...prev, instance: id }) })
  const setMode = (m: LiveViewMode) => navigate({ search: (prev) => ({ ...prev, mode: m }) })

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-6">
      <PageHeader
        title="Live"
        description="Running VMs: watch the display (view only) and follow the logs as they are written"
        actions={
          <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
            {MODES.map(({ value, label, icon: Icon }) => (
              <Button
                key={value}
                variant={mode === value ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setMode(value)}
              >
                <Icon size={14} />
                {label}
              </Button>
            ))}
          </div>
        }
      />

      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load running VMs."
        loadingFallback={<Skeleton className="h-24 w-full" />}
        isEmpty={instances.length === 0}
        emptyIcon={Activity}
        emptyTitle="No VMs running"
        emptyDescription="Start an experiment run or a dev session; its VM shows up here."
      >
        <div className="flex min-h-0 flex-1 gap-4">
          <ul className="w-60 shrink-0 space-y-2 overflow-auto">
            {instances.map((instance) => (
              <InstanceListItem
                key={String(instance.id)}
                instance={instance}
                selected={selected?.id === instance.id}
                onSelect={() => select(String(instance.id))}
              />
            ))}
          </ul>
          <div className="min-h-0 min-w-0 flex-1">
            {selected ? (
              <SelectedInstance instance={selected} mode={mode} />
            ) : (
              <EmptyState icon={Monitor} title="Select a VM" />
            )}
          </div>
        </div>
      </AsyncBoundary>
    </div>
  )
}
