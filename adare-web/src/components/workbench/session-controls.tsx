import { useEffect, useState } from 'react'
import { Plus, Square, RotateCcw, Trash2, Loader2 } from 'lucide-react'
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
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { FormField } from '@/components/ui/form-field'
import { Spinner } from '@/components/ui/spinner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { toast } from '@/components/ui/toast'
import {
  useSessions,
  useStartSession,
  useStopSession,
  useResetSession,
  useCleanupSessions,
} from '@/api/hooks/use-sessions'
import { useProjects } from '@/api/hooks/use-projects'
import { useExperiments } from '@/api/hooks/use-experiments'
import { useEnvironments } from '@/api/hooks/use-environments'
import type { StartSessionRequest } from '@/types/session'

const selectClass =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

interface Props {
  sessionId: string
  onSelectSession: (id: string) => void
  /** Pre-fill the new-session dialog (from `?experiment=` / `?environment=`). */
  initialExperiment?: string
  initialEnvironment?: string
  /** Open the new-session dialog immediately on mount. */
  autoOpenNew?: boolean
}

export function SessionControls({
  sessionId,
  onSelectSession,
  initialExperiment,
  initialEnvironment,
  autoOpenNew,
}: Props) {
  const { data: sessions, isPending: sessionsPending } = useSessions()
  const stopSession = useStopSession()
  const resetSession = useResetSession()
  const cleanupSessions = useCleanupSessions()

  const [dialogOpen, setDialogOpen] = useState(!!autoOpenNew)
  const [confirmStop, setConfirmStop] = useState(false)
  const [confirmHardReset, setConfirmHardReset] = useState(false)

  const selected = sessions?.find((s) => s.session_id === sessionId)

  const handleStop = () => {
    if (!sessionId) return
    stopSession.mutate(sessionId, {
      onSuccess: () => {
        toast.success('Session stopped')
        setConfirmStop(false)
      },
      onError: (err) => toast.error('Failed to stop session', (err as Error)?.message),
    })
  }

  const handleReset = (type: 'soft' | 'hard') => {
    if (!sessionId) return
    resetSession.mutate(
      { sessionId, type },
      {
        onSuccess: () => {
          toast.success(`Session reset (${type})`)
          setConfirmHardReset(false)
        },
        onError: (err) => toast.error('Failed to reset session', (err as Error)?.message),
      },
    )
  }

  const handleCleanup = () => {
    cleanupSessions.mutate(undefined, {
      onSuccess: (count) => toast.success('Cleanup complete', `${count} stale session(s) removed`),
      onError: (err) => toast.error('Cleanup failed', (err as Error)?.message),
    })
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-[280px] flex-1 space-y-1.5">
        <Label htmlFor="wb-session">Session</Label>
        <select
          id="wb-session"
          value={sessionId}
          onChange={(e) => onSelectSession(e.target.value)}
          className={selectClass}
        >
          <option value="">
            {sessionsPending ? 'Loading sessions…' : 'Select a session…'}
          </option>
          {sessions?.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.experiment} · {s.environment} ({s.session_id.slice(0, 8)})
              {s.vm_running === false ? ' · stopped' : ''}
            </option>
          ))}
        </select>
      </div>

      <Button onClick={() => setDialogOpen(true)}>
        <Plus size={14} />
        New session
      </Button>

      <Button
        variant="outline"
        disabled={!sessionId || stopSession.isPending}
        onClick={() => setConfirmStop(true)}
      >
        <Square size={14} />
        Stop
      </Button>

      <Button
        variant="outline"
        disabled={!sessionId || resetSession.isPending}
        onClick={() => handleReset('soft')}
        title="Soft reset: clear variables and state without rewinding VM disk"
      >
        <RotateCcw size={14} />
        Soft reset
      </Button>

      <Button
        variant="outline"
        disabled={!sessionId || resetSession.isPending}
        onClick={() => setConfirmHardReset(true)}
        title="Hard reset: rewind the VM to its initial state"
      >
        <RotateCcw size={14} />
        Hard reset
      </Button>

      <Button
        variant="ghost"
        disabled={cleanupSessions.isPending}
        onClick={handleCleanup}
        title="Remove stale / orphaned sessions"
      >
        {cleanupSessions.isPending ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Trash2 size={14} />
        )}
        Cleanup stale
      </Button>

      <NewSessionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initialExperiment={initialExperiment}
        initialEnvironment={initialEnvironment}
        onCreated={onSelectSession}
      />

      <ConfirmDialog
        open={confirmStop}
        onOpenChange={setConfirmStop}
        title="Stop session"
        description={`Stop session "${selected?.session_id.slice(0, 8) ?? ''}"? The VM will be shut down.`}
        confirmLabel="Stop"
        variant="destructive"
        loading={stopSession.isPending}
        onConfirm={handleStop}
      />

      <ConfirmDialog
        open={confirmHardReset}
        onOpenChange={setConfirmHardReset}
        title="Hard reset session"
        description="Rewind the VM to its initial state? All progress since the session started will be lost."
        confirmLabel="Hard reset"
        variant="destructive"
        loading={resetSession.isPending}
        onConfirm={() => handleReset('hard')}
      />
    </div>
  )
}

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialExperiment?: string
  initialEnvironment?: string
  onCreated: (sessionId: string) => void
}

function NewSessionDialog({
  open,
  onOpenChange,
  initialExperiment,
  initialEnvironment,
  onCreated,
}: DialogProps) {
  const projectsQuery = useProjects()
  const experimentsQuery = useExperiments()
  const environmentsQuery = useEnvironments()
  const startSession = useStartSession()

  const [projectPath, setProjectPath] = useState('')
  const [experimentName, setExperimentName] = useState(initialExperiment ?? '')
  const [environmentName, setEnvironmentName] = useState(initialEnvironment ?? '')
  const [guiMode, setGuiMode] = useState('')
  const [vmMemory, setVmMemory] = useState('')
  const [vmCpus, setVmCpus] = useState('')
  const [debugScreenshots, setDebugScreenshots] = useState(false)

  useEffect(() => {
    if (!open) {
      startSession.reset()
      return
    }
    setExperimentName(initialExperiment ?? '')
    setEnvironmentName(initialEnvironment ?? '')
  }, [open, initialExperiment, initialEnvironment, startSession])

  useEffect(() => {
    if (open && !projectPath && projectsQuery.data && projectsQuery.data.length > 0) {
      setProjectPath(String(projectsQuery.data[0].path))
    }
  }, [open, projectPath, projectsQuery.data])

  const canSubmit =
    projectPath.trim().length > 0 &&
    experimentName.trim().length > 0 &&
    environmentName.trim().length > 0 &&
    !startSession.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    const parsedMem = parseInt(vmMemory, 10)
    const parsedCpus = parseInt(vmCpus, 10)
    const request: StartSessionRequest = {
      project_path: projectPath.trim(),
      experiment_name: experimentName.trim(),
      environment_name: environmentName.trim(),
      ...(guiMode.trim() ? { gui_mode: guiMode.trim() } : {}),
      ...(Number.isFinite(parsedMem) && parsedMem > 0 ? { vm_memory: parsedMem } : {}),
      ...(Number.isFinite(parsedCpus) && parsedCpus > 0 ? { vm_cpus: parsedCpus } : {}),
      ...(debugScreenshots ? { debug_screenshots: true } : {}),
    }
    startSession.mutate(request, {
      onSuccess: (session) => {
        toast.success('Session started', session.session_id.slice(0, 8))
        onCreated(session.session_id)
        onOpenChange(false)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>New session</DialogTitle>
            <DialogDescription>
              Start an interactive dev session against a live VM.
            </DialogDescription>
          </DialogHeader>

          <FormField label="Project" htmlFor="ns-project" required>
            <select
              id="ns-project"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              className={selectClass}
            >
              <option value="">Select a project…</option>
              {projectsQuery.data?.map((p) => (
                <option key={String(p.path)} value={String(p.path)}>
                  {p.name} ({String(p.path)})
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Experiment" htmlFor="ns-experiment" required>
            <select
              id="ns-experiment"
              value={experimentName}
              onChange={(e) => setExperimentName(e.target.value)}
              className={selectClass}
            >
              <option value="">Select an experiment…</option>
              {experimentsQuery.data?.map((exp) => (
                <option key={exp.name} value={exp.name}>
                  {exp.name}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Environment" htmlFor="ns-environment" required>
            <select
              id="ns-environment"
              value={environmentName}
              onChange={(e) => setEnvironmentName(e.target.value)}
              className={selectClass}
            >
              <option value="">Select an environment…</option>
              {environmentsQuery.data?.map((env) => (
                <option key={env.name} value={env.name}>
                  {env.name}
                </option>
              ))}
            </select>
          </FormField>

          <div className="grid grid-cols-2 gap-4">
            <FormField label="GUI mode" htmlFor="ns-gui-mode" hint="Optional">
              <Input
                id="ns-gui-mode"
                value={guiMode}
                onChange={(e) => setGuiMode(e.target.value)}
                placeholder="Default"
              />
            </FormField>
            <div className="flex items-end">
              <label className="flex items-center gap-2 pb-2.5 text-sm">
                <Checkbox
                  checked={debugScreenshots}
                  onChange={(e) => setDebugScreenshots(e.target.checked)}
                />
                Debug screenshots
              </label>
            </div>
            <FormField label="VM memory (MB)" htmlFor="ns-vm-memory" hint="Optional">
              <Input
                id="ns-vm-memory"
                type="number"
                min={1}
                value={vmMemory}
                onChange={(e) => setVmMemory(e.target.value)}
                placeholder="Default"
              />
            </FormField>
            <FormField label="VM CPUs" htmlFor="ns-vm-cpus" hint="Optional">
              <Input
                id="ns-vm-cpus"
                type="number"
                min={1}
                value={vmCpus}
                onChange={(e) => setVmCpus(e.target.value)}
                placeholder="Default"
              />
            </FormField>
          </div>

          {startSession.isError && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {(startSession.error as Error)?.message ?? 'Failed to start session.'}
            </div>
          )}

          <DialogFooter className="gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={startSession.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {startSession.isPending && <Spinner className="h-4 w-4" />}
              Start session
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
