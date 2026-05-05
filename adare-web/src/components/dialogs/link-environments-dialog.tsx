import { useState, useEffect, useMemo } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Spinner } from '@/components/ui/spinner'
import {
  useAddExperimentEnvironments,
  useRemoveExperimentEnvironments,
  type Experiment,
} from '@/api/hooks/use-experiments'
import { useEnvironments } from '@/api/hooks/use-environments'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  experiment: Experiment | null
}

export function LinkEnvironmentsDialog({ open, onOpenChange, experiment }: Props) {
  const envsQuery = useEnvironments()
  const addMutation = useAddExperimentEnvironments()
  const removeMutation = useRemoveExperimentEnvironments()

  const initialSelected = useMemo(
    () => new Set<string>(experiment?.environment_names ?? []),
    [experiment],
  )

  const [selected, setSelected] = useState<Set<string>>(initialSelected)
  const [error, setError] = useState<string | null>(null)

  // Re-sync whenever the dialog opens or the target experiment changes.
  useEffect(() => {
    if (open) {
      setSelected(new Set(experiment?.environment_names ?? []))
      setError(null)
      addMutation.reset()
      removeMutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, experiment?.name])

  const toggleEnv = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const diff = useMemo(() => {
    const prev = new Set(experiment?.environment_names ?? [])
    const added: string[] = []
    const removed: string[] = []
    for (const name of selected) if (!prev.has(name)) added.push(name)
    for (const name of prev) if (!selected.has(name)) removed.push(name)
    return { added, removed }
  }, [selected, experiment])

  const isPending = addMutation.isPending || removeMutation.isPending
  const hasChanges = diff.added.length > 0 || diff.removed.length > 0

  const projectPath = experiment
    ? String(
        (experiment as { project_path?: string; project?: string }).project_path ??
          (experiment as { project?: string }).project ??
          '',
      )
    : ''

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!experiment || !hasChanges || !projectPath) {
      if (!projectPath) setError('Experiment has no project path; cannot link environments.')
      return
    }
    setError(null)
    try {
      if (diff.added.length > 0) {
        await addMutation.mutateAsync({
          name: experiment.name,
          request: { project_path: projectPath, environments: diff.added },
        })
      }
      if (diff.removed.length > 0) {
        await removeMutation.mutateAsync({
          name: experiment.name,
          request: { project_path: projectPath, environments: diff.removed },
        })
      }
      const parts: string[] = []
      if (diff.added.length > 0) parts.push(`+${diff.added.length} linked`)
      if (diff.removed.length > 0) parts.push(`-${diff.removed.length} unlinked`)
      toast.success('Environments updated', parts.join(', '))
      onOpenChange(false)
    } catch (err) {
      setError((err as Error)?.message ?? 'Failed to update environments.')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Link environments</DialogTitle>
            <DialogDescription>
              {experiment
                ? `Select environments to link with "${experiment.name}".`
                : 'Select environments'}
            </DialogDescription>
          </DialogHeader>

          <div className="max-h-72 overflow-y-auto rounded-md border border-border p-2">
            {envsQuery.isPending && (
              <div className="p-2 text-xs text-muted-foreground">Loading environments…</div>
            )}
            {!envsQuery.isPending && (envsQuery.data?.length ?? 0) === 0 && (
              <div className="p-2 text-xs text-muted-foreground">
                No environments available. Create one first.
              </div>
            )}
            {envsQuery.data?.map((env) => (
              <label
                key={env.name}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-muted/50"
              >
                <Checkbox
                  checked={selected.has(env.name)}
                  onChange={() => toggleEnv(env.name)}
                />
                <span className="text-sm">{env.name}</span>
              </label>
            ))}
          </div>

          {hasChanges && (
            <div className="text-xs text-muted-foreground">
              Changes: {diff.added.length > 0 && <>+{diff.added.join(', ')} </>}
              {diff.removed.length > 0 && <>−{diff.removed.join(', ')}</>}
            </div>
          )}

          {error && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <DialogFooter className="gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!hasChanges || isPending}>
              {isPending && <Spinner className="h-4 w-4" />}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
