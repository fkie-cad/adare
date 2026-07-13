import { useState } from 'react'
import { Server, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
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

      {isPending && <LoadingTable />}

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-6 flex items-center gap-4">
            <p className="text-sm text-destructive flex-1">
              {(error as Error)?.message ?? 'Failed to load environments.'}
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw size={14} />
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {!isPending && !isError && data?.length === 0 && (
        <EmptyState
          icon={Server}
          title="No environments"
          description="Create an environment to run experiments against."
        />
      )}

      {!isPending && !isError && data && data.length > 0 && (
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
            {data.map((env) => (
              <TableRow key={env.name} className="hover:bg-muted/50">
                <TableCell className="font-medium">{env.name}</TableCell>
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
            {data.length} environment{data.length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      )}

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
