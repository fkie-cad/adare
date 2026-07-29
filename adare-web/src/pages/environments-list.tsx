import { useState } from 'react'
import { Server, Plus, Trash2 } from 'lucide-react'
import { Link } from '@tanstack/react-router'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CreateEnvironmentDialog } from '@/components/dialogs/create-environment-dialog'
import { useEnvironments, useDeleteEnvironment, type Environment } from '@/api/hooks/use-environments'
import { toast } from '@/components/ui/toast'

const SKELETON_ROWS = 5
const COLUMNS = 7

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>OS</TableHead>
          <TableHead>VM</TableHead>
          <TableHead>Project</TableHead>
          <TableHead>Sync</TableHead>
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

function SyncBadge({ synced }: { synced: unknown }) {
  if (synced === true) return <Badge variant="success">Synced</Badge>
  if (synced === false) return <Badge variant="warning">Unsynced</Badge>
  return <>—</>
}

function EnvironmentTypeBadge({ env }: { env: Environment }) {
  if (env.recipe) return <Badge variant="secondary">Recipe</Badge>
  if (env.vm_type === 'path' || env.vm_type === 'url' || env.vm) {
    return <Badge variant="outline">Baked</Badge>
  }
  return <Badge variant="outline">Legacy</Badge>
}

function isUrl(value?: string): value is string {
  return !!value && /^https?:\/\//i.test(value)
}

function VmCell({ env }: { env: Environment }) {
  if (isUrl(env.vm) || (env.vm_type === 'url' && env.vm)) {
    return (
      <a
        href={env.vm}
        target="_blank"
        rel="noreferrer"
        className="font-mono text-xs text-primary underline underline-offset-2 hover:no-underline break-all"
      >
        {env.vm}
      </a>
    )
  }
  if (env.vm) {
    return <span className="font-mono text-xs break-all">{env.vm}</span>
  }
  return <>—</>
}

export default function EnvironmentsListPage() {
  const { data, isPending, isError, error, refetch } = useEnvironments()
  const deleteMutation = useDeleteEnvironment()
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Environment | null>(null)

  const handleDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(
      { name: deleteTarget.name },
      {
        onSuccess: () => {
          toast.success('Environment removed', deleteTarget.name)
          setDeleteTarget(null)
        },
        onError: (err) => {
          toast.error('Failed to remove environment', (err as Error)?.message)
        },
      },
    )
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Environments"
        description="VM environments for running experiments"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={16} />
            New environment
          </Button>
        }
      />

      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load environments."
        loadingFallback={<LoadingTable />}
        isEmpty={data?.length === 0}
        emptyIcon={Server}
        emptyTitle="No environments"
        emptyDescription="Create an environment to run experiments against."
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>OS</TableHead>
              <TableHead>VM</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Sync</TableHead>
              <TableHead className="w-24 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((env) => (
              <TableRow key={env.name} className="hover:bg-muted/50">
                <TableCell className="font-medium">
                  <Link to="/environments/$name" params={{ name: env.name }} className="hover:underline">
                    {env.name}
                  </Link>
                </TableCell>
                <TableCell>
                  <EnvironmentTypeBadge env={env} />
                </TableCell>
                <TableCell>{(env as any).os || '—'}</TableCell>
                <TableCell className="max-w-xs">
                  <VmCell env={env} />
                </TableCell>
                <TableCell>
                  {env.project_path ? (
                    <span className="font-mono text-xs">{env.project_path}</span>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>
                  <SyncBadge synced={(env as any).synced} />
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete environment"
                    onClick={() => setDeleteTarget(env)}
                  >
                    <Trash2 size={16} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>
            {(data ?? []).length} environment{(data ?? []).length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      </AsyncBoundary>

      <CreateEnvironmentDialog open={createOpen} onOpenChange={setCreateOpen} />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Remove environment"
        description={
          deleteTarget
            ? `Are you sure you want to remove "${deleteTarget.name}"? This cannot be undone.`
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
