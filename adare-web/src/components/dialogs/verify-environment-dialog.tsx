import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { useVerifyEnvironment } from '@/api/hooks/use-environments'
import { toast } from '@/components/ui/toast'

interface VerifyEnvironmentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  environmentName: string | null
  projectPath: string | null
  onSkip?: () => void
}

export function VerifyEnvironmentDialog({
  open,
  onOpenChange,
  environmentName,
  projectPath,
  onSkip,
}: VerifyEnvironmentDialogProps) {
  const mutation = useVerifyEnvironment()
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) {
      mutation.reset()
    }
  }, [open, mutation])

  if (!environmentName || !projectPath) {
    return null
  }

  const handleSkip = () => {
    onSkip?.()
    onOpenChange(false)
  }

  const handleRun = () => {
    mutation.mutate(
      { name: environmentName, project_path: projectPath },
      {
        onSuccess: (data) => {
          onOpenChange(false)
          navigate({ to: '/runs', search: { focus: data.run_ulid } })
          toast.success('Verification started', 'Status will appear in the runs list.')
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <div className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Environment created</DialogTitle>
            <DialogDescription>
              Want to run a quick verification? It exercises boot, agent install, screenshot,
              command, and action dispatch — about 1–2 minutes.
            </DialogDescription>
          </DialogHeader>

          {mutation.isError && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {(mutation.error as Error)?.message ?? 'Failed to start verification.'}
            </div>
          )}

          <DialogFooter className="gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleSkip}
              disabled={mutation.isPending}
            >
              Skip
            </Button>
            <Button type="button" onClick={handleRun} disabled={mutation.isPending}>
              {mutation.isPending && <Spinner className="h-4 w-4" />}
              Run quick test
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}
