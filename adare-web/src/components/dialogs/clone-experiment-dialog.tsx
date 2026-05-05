import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { FormField } from '@/components/ui/form-field'
import { Spinner } from '@/components/ui/spinner'
import { useCloneExperiment, type Experiment } from '@/api/hooks/use-experiments'
import { useEnvironments } from '@/api/hooks/use-environments'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  source: Experiment | null
}

export function CloneExperimentDialog({ open, onOpenChange, source }: Props) {
  const envsQuery = useEnvironments()
  const [target, setTarget] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const mutation = useCloneExperiment()

  useEffect(() => {
    if (!open) {
      setTarget('')
      setSelected(new Set())
      mutation.reset()
    } else if (source) {
      // Pre-fill with the source experiment's envs.
      setSelected(new Set(source.environment_names ?? []))
    }
  }, [open, source, mutation])

  const canSubmit =
    !!source &&
    target.trim().length > 0 &&
    target.trim() !== source?.name &&
    !mutation.isPending

  const toggleEnv = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit || !source) return
    const projectPath = String((source as { project_path?: string; project?: string }).project_path ?? (source as { project?: string }).project ?? '')
    mutation.mutate(
      {
        name: source.name,
        request: {
          project_path: projectPath,
          target_experiment: target.trim(),
          environments: selected.size > 0 ? Array.from(selected) : undefined,
        },
      },
      {
        onSuccess: () => {
          toast.success('Experiment cloned', `${source.name} → ${target.trim()}`)
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Clone experiment</DialogTitle>
            <DialogDescription>
              {source ? `Clone "${source.name}" into a new experiment.` : 'Clone experiment'}
            </DialogDescription>
          </DialogHeader>

          <FormField label="Target name" htmlFor="clone-target" required>
            <Input
              id="clone-target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="new-experiment-name"
              autoFocus
            />
          </FormField>

          <FormField label="Environments" hint="Subset of environments to clone. Leave empty to keep all.">
            <div className="max-h-48 overflow-y-auto rounded-md border border-border p-2">
              {envsQuery.isPending && (
                <div className="text-xs text-muted-foreground">Loading environments…</div>
              )}
              {envsQuery.data?.length === 0 && (
                <div className="text-xs text-muted-foreground">No environments available.</div>
              )}
              {envsQuery.data?.map((env) => (
                <label
                  key={env.name}
                  className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-muted/50"
                >
                  <Checkbox
                    checked={selected.has(env.name)}
                    onChange={() => toggleEnv(env.name)}
                  />
                  <span className="text-sm">{env.name}</span>
                </label>
              ))}
            </div>
          </FormField>

          {mutation.isError && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {(mutation.error as Error)?.message ?? 'Failed to clone experiment.'}
            </div>
          )}

          <DialogFooter className="gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {mutation.isPending && <Spinner className="h-4 w-4" />}
              Clone
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
