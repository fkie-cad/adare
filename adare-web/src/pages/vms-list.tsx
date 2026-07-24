import { useState } from 'react'
import { HardDrive, RefreshCw, Trash2 } from 'lucide-react'
import { Link } from '@tanstack/react-router'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useLocalVms, useDeleteLocalVm, useRemoveAllStoppedInstances, type LocalVm } from '@/api/hooks/use-vms'
import { toast } from '@/components/ui/toast'

const SKELETON_ROWS = 5
const COLUMNS = 3

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Path</TableHead>
          <TableHead className="w-24 text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
          <TableRow key={i}>
            {Array.from({ length: COLUMNS }).map((_, j) => (
              <TableCell key={j}>
                <Skeleton className="h-4 w-full" />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export default function VmsListPage() {
  const { data, isPending, isError, error, refetch } = useLocalVms()
  const deleteMutation = useDeleteLocalVm()
  const cleanupMutation = useRemoveAllStoppedInstances()
  const [deleteTarget, setDeleteTarget] = useState<LocalVm | null>(null)

  const handleDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(
      { vmId: deleteTarget.id, force: true },
      {
        onSuccess: () => {
          toast.success('VM removed', deleteTarget.name ?? deleteTarget.id)
          setDeleteTarget(null)
        },
        onError: (err) => toast.error('Failed to remove VM', (err as Error)?.message),
      },
    )
  }

  const handleCleanup = () => {
    cleanupMutation.mutate(undefined, {
      onSuccess: (count) => toast.success('Cleanup complete', `Removed ${count} stopped instance${count === 1 ? '' : 's'}`),
      onError: (err) => toast.error('Cleanup failed', (err as Error)?.message),
    })
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="VMs"
        description="Registered VM images and their running instances"
        actions={
          <Button variant="outline" onClick={handleCleanup} disabled={cleanupMutation.isPending}>
            <RefreshCw size={14} className={cleanupMutation.isPending ? 'animate-spin' : undefined} />
            Remove stopped instances
          </Button>
        }
      />

      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load VMs."
        loadingFallback={<LoadingTable />}
        isEmpty={data?.length === 0}
        emptyIcon={HardDrive}
        emptyTitle="No VMs registered"
        emptyDescription="Load a VM to see it here."
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Path</TableHead>
              <TableHead className="w-24 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((vm) => (
              <TableRow key={vm.id} className="hover:bg-muted/50">
                <TableCell className="font-medium">
                  <Link to="/vms/$instanceId" params={{ instanceId: vm.id }} className="hover:underline">
                    {vm.name || vm.id}
                  </Link>
                </TableCell>
                <TableCell>
                  {vm.path ? <span className="font-mono text-xs break-all">{vm.path}</span> : '—'}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete VM"
                    onClick={() => setDeleteTarget(vm)}
                  >
                    <Trash2 size={16} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>{(data ?? []).length} VM{(data ?? []).length === 1 ? '' : 's'}</TableCaption>
        </Table>
      </AsyncBoundary>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Remove VM"
        description={
          deleteTarget
            ? `Are you sure you want to remove "${deleteTarget.name ?? deleteTarget.id}"? This cannot be undone.`
            : undefined
        }
        confirmLabel="Remove"
        variant="destructive"
        loading={deleteMutation.isPending}
        onConfirm={handleDelete}
      />
    </div>
  )
}
