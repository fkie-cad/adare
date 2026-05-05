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
import { Textarea } from '@/components/ui/textarea'
import { FormField } from '@/components/ui/form-field'
import { Spinner } from '@/components/ui/spinner'
import { useCreateProject } from '@/api/hooks/use-projects'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateProjectDialog({ open, onOpenChange }: Props) {
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [description, setDescription] = useState('')
  const mutation = useCreateProject()

  useEffect(() => {
    if (!open) {
      setName('')
      setPath('')
      setDescription('')
      mutation.reset()
    }
  }, [open, mutation])

  const canSubmit = name.trim().length > 0 && path.trim().length > 0 && !mutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    mutation.mutate(
      { name: name.trim(), path: path.trim(), description: description.trim() || undefined },
      {
        onSuccess: () => {
          toast.success('Project created', name.trim())
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
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>Register a new project with ADARE.</DialogDescription>
          </DialogHeader>

          <FormField label="Name" htmlFor="proj-name" required>
            <Input
              id="proj-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-project"
              autoFocus
            />
          </FormField>

          <FormField label="Path" htmlFor="proj-path" required hint="Absolute filesystem path">
            <Input
              id="proj-path"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/absolute/path/to/project"
            />
          </FormField>

          <FormField label="Description" htmlFor="proj-description">
            <Textarea
              id="proj-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
            />
          </FormField>

          {mutation.isError && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {(mutation.error as Error)?.message ?? 'Failed to create project.'}
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
