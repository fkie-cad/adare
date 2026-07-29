import { useState } from 'react'
import { Camera, ChevronDown, ChevronRight, History, Trash2, Plus, Loader2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { toast } from '@/components/ui/toast'
import { formatDateTime } from '@/lib/formatters'
import {
  useCheckpoints,
  useCreateCheckpoint,
  useRestoreCheckpoint,
  useDeleteCheckpoint,
} from '@/api/hooks/use-checkpoints'

interface Props {
  sessionId: string
}

export function CheckpointsPanel({ sessionId }: Props) {
  const { data: checkpoints, isPending, isError, error, refetch } = useCheckpoints(sessionId)
  const createCheckpoint = useCreateCheckpoint(sessionId)
  const restoreCheckpoint = useRestoreCheckpoint(sessionId)
  const deleteCheckpoint = useDeleteCheckpoint(sessionId)

  const [collapsed, setCollapsed] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [restoreTarget, setRestoreTarget] = useState<string | null>(null)

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createCheckpoint.mutate(
      { name: name.trim(), description: description.trim() || undefined },
      {
        onSuccess: () => {
          toast.success('Checkpoint created', name.trim())
          setName('')
          setDescription('')
        },
        onError: (err) => toast.error('Failed to create checkpoint', (err as Error)?.message),
      },
    )
  }

  const handleRestore = () => {
    if (!restoreTarget) return
    restoreCheckpoint.mutate(restoreTarget, {
      onSuccess: () => {
        toast.success('Checkpoint restored', restoreTarget)
        setRestoreTarget(null)
      },
      onError: (err) => toast.error('Failed to restore', (err as Error)?.message),
    })
  }

  const handleDelete = (cpName: string) => {
    deleteCheckpoint.mutate(cpName, {
      onSuccess: () => toast.success('Checkpoint deleted', cpName),
      onError: (err) => toast.error('Failed to delete', (err as Error)?.message),
    })
  }

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <button
          type="button"
          className="flex w-full items-center gap-2 text-sm font-semibold"
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          <History size={16} />
          Checkpoints
          {checkpoints && checkpoints.length > 0 && (
            <span className="ml-auto text-xs font-normal text-muted-foreground">
              {checkpoints.length}
            </span>
          )}
        </button>

        {!collapsed && (
          <>
            <form onSubmit={handleCreate} className="space-y-2">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Checkpoint name"
              />
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Description (optional)"
              />
              <Button
                type="submit"
                size="sm"
                className="w-full"
                disabled={!name.trim() || createCheckpoint.isPending}
              >
                {createCheckpoint.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Plus size={14} />
                )}
                New checkpoint
              </Button>
            </form>

            <AsyncBoundary
              isPending={isPending}
              isError={isError}
              error={error}
              onRetry={() => refetch()}
              loadingFallback={<p className="text-sm text-muted-foreground">Loading…</p>}
              isEmpty={checkpoints?.length === 0}
              emptyIcon={Camera}
              emptyTitle="No checkpoints"
              emptyDescription="Snapshot VM state to rewind to later."
            >
              <div className="space-y-2">
                {checkpoints?.map((cp) => (
                  <div key={cp.name} className="rounded-md border border-border p-2.5 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{cp.name}</span>
                      <div className="ml-auto flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Restore"
                          onClick={() => setRestoreTarget(cp.name)}
                        >
                          <History size={14} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Delete"
                          onClick={() => handleDelete(cp.name)}
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    </div>
                    {cp.description && (
                      <p className="text-xs text-muted-foreground">{cp.description}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(cp.created_at)} · {cp.memory_size_mb}MB mem ·{' '}
                      {cp.disk_size_mb}MB disk
                    </p>
                  </div>
                ))}
              </div>
            </AsyncBoundary>
          </>
        )}
      </CardContent>

      <ConfirmDialog
        open={!!restoreTarget}
        onOpenChange={(open) => !open && setRestoreTarget(null)}
        title="Restore checkpoint"
        description={
          restoreTarget
            ? `Rewind the VM to checkpoint "${restoreTarget}"? Current unsaved VM state will be lost.`
            : undefined
        }
        confirmLabel="Restore"
        variant="destructive"
        loading={restoreCheckpoint.isPending}
        onConfirm={handleRestore}
      />
    </Card>
  )
}
