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
import { FormField } from '@/components/ui/form-field'
import { Spinner } from '@/components/ui/spinner'
import { useCreateEnvironment } from '@/api/hooks/use-environments'
import { useProjects } from '@/api/hooks/use-projects'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultProjectPath?: string
}

export function CreateEnvironmentDialog({ open, onOpenChange, defaultProjectPath }: Props) {
  const projectsQuery = useProjects()
  const [projectPath, setProjectPath] = useState(defaultProjectPath ?? '')
  const [name, setName] = useState('')
  const [vmPath, setVmPath] = useState('')
  const mutation = useCreateEnvironment()

  useEffect(() => {
    if (!open) {
      setName('')
      setVmPath('')
      mutation.reset()
      setProjectPath(defaultProjectPath ?? '')
    }
  }, [open, defaultProjectPath, mutation])

  // Default to the first project once loaded (if none selected yet).
  useEffect(() => {
    if (open && !projectPath && projectsQuery.data && projectsQuery.data.length > 0) {
      setProjectPath(String(projectsQuery.data[0].path))
    }
  }, [open, projectPath, projectsQuery.data])

  const canSubmit =
    projectPath.trim().length > 0 && name.trim().length > 0 && !mutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    mutation.mutate(
      {
        project_path: projectPath.trim(),
        name: name.trim(),
        vm_path: vmPath.trim() || undefined,
      },
      {
        onSuccess: () => {
          toast.success('Environment created', name.trim())
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
            <DialogTitle>New environment</DialogTitle>
            <DialogDescription>Define an environment within a project.</DialogDescription>
          </DialogHeader>

          <FormField label="Project" htmlFor="env-project" required>
            <select
              id="env-project"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="">Select a project…</option>
              {projectsQuery.data?.map((p) => (
                <option key={String(p.path)} value={String(p.path)}>
                  {p.name} ({String(p.path)})
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Name" htmlFor="env-name" required>
            <Input
              id="env-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ubuntu24"
              autoFocus
            />
          </FormField>

          <FormField label="VM path" htmlFor="env-vm-path" hint="Optional path to an existing VM">
            <Input
              id="env-vm-path"
              value={vmPath}
              onChange={(e) => setVmPath(e.target.value)}
              placeholder="/path/to/vm"
            />
          </FormField>

          {mutation.isError && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {(mutation.error as Error)?.message ?? 'Failed to create environment.'}
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
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
