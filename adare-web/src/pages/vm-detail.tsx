import { useState } from 'react'
import { useParams, useNavigate } from '@tanstack/react-router'
import { Camera, Eye, HardDrive, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { VmLiveView } from '@/components/vm/vm-live-view'
import {
  useLocalVm,
  useDeleteLocalVm,
  useVmInstances,
  useRemoveVmInstance,
  useVmSnapshots,
  useDeleteVmSnapshot,
  type VmInstance,
} from '@/api/hooks/use-vms'
import { toast } from '@/components/ui/toast'

function SnapshotsPanel({ instanceId }: { instanceId: string }) {
  const { data, isPending, isError, error, refetch } = useVmSnapshots(instanceId)
  const deleteMutation = useDeleteVmSnapshot(instanceId)

  return (
    <div className="space-y-2">
      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load snapshots."
        loadingFallback={<Skeleton className="h-8 w-full" />}
        isEmpty={data?.length === 0}
        emptyTitle="No snapshots"
        emptyDescription="Create one from an active dev session to see it here."
      >
        <ul className="space-y-1">
          {(data ?? []).map((snap) => (
            <li
              key={snap.name}
              className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
            >
              <span className="font-mono">{snap.name}</span>
              <Button
                variant="ghost"
                size="icon"
                title="Delete snapshot"
                onClick={() =>
                  deleteMutation.mutate(snap.name, {
                    onSuccess: () => toast.success('Snapshot removed', snap.name),
                    onError: (err) => toast.error('Failed to remove snapshot', (err as Error)?.message),
                  })
                }
              >
                <Trash2 size={14} />
              </Button>
            </li>
          ))}
        </ul>
      </AsyncBoundary>
    </div>
  )
}

function InstanceRow({ instance }: { instance: VmInstance }) {
  const [expanded, setExpanded] = useState<'live' | 'snapshots' | null>(null)
  const removeMutation = useRemoveVmInstance()
  const vmName = String(instance.name ?? instance.id)

  return (
    <div className="rounded-md border border-border">
      <div className="flex items-center gap-3 p-3">
        <Badge variant={statusToVariant(instance.status ?? null)}>{instance.status ?? '—'}</Badge>
        <span className="font-mono text-sm">{vmName}</span>
        {typeof instance.websocket_port === 'number' && (
          <span className="text-xs text-muted-foreground">port {instance.websocket_port}</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant={expanded === 'live' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setExpanded((e) => (e === 'live' ? null : 'live'))}
          >
            <Eye size={14} />
            Watch
          </Button>
          <Button
            variant={expanded === 'snapshots' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setExpanded((e) => (e === 'snapshots' ? null : 'snapshots'))}
          >
            <Camera size={14} />
            Snapshots
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Remove instance"
            onClick={() =>
              removeMutation.mutate(String(instance.id), {
                onSuccess: () => toast.success('Instance removed', vmName),
                onError: (err) => toast.error('Failed to remove instance', (err as Error)?.message),
              })
            }
          >
            <Trash2 size={16} />
          </Button>
        </div>
      </div>

      {expanded === 'live' && (
        <div className="border-t border-border h-[420px]">
          <VmLiveView vmName={vmName} className="h-full" />
        </div>
      )}

      {expanded === 'snapshots' && (
        <div className="border-t border-border p-3">
          <SnapshotsPanel instanceId={String(instance.id)} />
        </div>
      )}
    </div>
  )
}

export default function VmDetailPage() {
  const { instanceId: vmId } = useParams({ from: '/vms/$instanceId' })
  const navigate = useNavigate()
  const vmQuery = useLocalVm(vmId)
  const instancesQuery = useVmInstances(vmId)
  const deleteMutation = useDeleteLocalVm()

  const handleDeleteVm = () => {
    deleteMutation.mutate(
      { vmId, force: true },
      {
        onSuccess: () => {
          toast.success('VM removed', vmQuery.data?.name ?? vmId)
          navigate({ to: '/vms' })
        },
        onError: (err) => toast.error('Failed to remove VM', (err as Error)?.message),
      },
    )
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title={vmQuery.data?.name || vmId}
        description={vmQuery.data?.path ? String(vmQuery.data.path) : undefined}
        actions={
          <Button variant="outline" onClick={handleDeleteVm} disabled={deleteMutation.isPending}>
            <Trash2 size={14} />
            Delete VM
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Running instances</CardTitle>
        </CardHeader>
        <CardContent>
          <AsyncBoundary
            isPending={instancesQuery.isPending}
            isError={instancesQuery.isError}
            error={instancesQuery.error}
            onRetry={() => instancesQuery.refetch()}
            errorFallbackMessage="Failed to load instances."
            loadingFallback={<Skeleton className="h-10 w-full" />}
            isEmpty={instancesQuery.data?.length === 0}
            emptyIcon={HardDrive}
            emptyTitle="No running instances"
            emptyDescription="Start a dev session against this VM to see it here."
          >
            <div className="space-y-2">
              {(instancesQuery.data ?? []).map((instance) => (
                <InstanceRow key={String(instance.id)} instance={instance} />
              ))}
            </div>
          </AsyncBoundary>
        </CardContent>
      </Card>
    </div>
  )
}
