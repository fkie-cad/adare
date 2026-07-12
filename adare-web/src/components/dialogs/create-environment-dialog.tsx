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
import { useCreateEnvironment, useOsProfiles } from '@/api/hooks/use-environments'
import { useProjects } from '@/api/hooks/use-projects'
import { toast } from '@/components/ui/toast'
import { VerifyEnvironmentDialog } from '@/components/dialogs/verify-environment-dialog'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultProjectPath?: string
}

type EnvironmentMode = 'baked' | 'recipe'

const selectClassName =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'

export function CreateEnvironmentDialog({ open, onOpenChange, defaultProjectPath }: Props) {
  const projectsQuery = useProjects()
  const osProfilesQuery = useOsProfiles()
  const [projectPath, setProjectPath] = useState(defaultProjectPath ?? '')
  const [name, setName] = useState('')
  const [mode, setMode] = useState<EnvironmentMode>('baked')
  const [vmPath, setVmPath] = useState('')
  const [osProfile, setOsProfile] = useState('')
  const [isoPath, setIsoPath] = useState('')
  const [diskSize, setDiskSize] = useState('')
  const [ramMb, setRamMb] = useState('')
  const [cpus, setCpus] = useState('')
  const [setupLevel, setSetupLevel] = useState('')
  const [verifyState, setVerifyState] = useState<{ name: string; projectPath: string } | null>(null)
  const mutation = useCreateEnvironment()

  useEffect(() => {
    if (!open) {
      setName('')
      setMode('baked')
      setVmPath('')
      setOsProfile('')
      setIsoPath('')
      setDiskSize('')
      setRamMb('')
      setCpus('')
      setSetupLevel('')
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

  // Default to the first OS profile once loaded (recipe mode only).
  useEffect(() => {
    if (open && mode === 'recipe' && !osProfile && osProfilesQuery.data && osProfilesQuery.data.length > 0) {
      setOsProfile(osProfilesQuery.data[0].name)
    }
  }, [open, mode, osProfile, osProfilesQuery.data])

  const canSubmit =
    projectPath.trim().length > 0 &&
    name.trim().length > 0 &&
    !mutation.isPending &&
    (mode === 'baked' || (osProfile.trim().length > 0 && isoPath.trim().length > 0))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    const submittedProjectPath = projectPath.trim()
    mutation.mutate(
      {
        project_path: submittedProjectPath,
        name: name.trim(),
        ...(mode === 'baked'
          ? { vm_path: vmPath.trim() || undefined }
          : {
              os_profile: osProfile,
              iso_path: isoPath.trim(),
              disk_size: diskSize.trim() || undefined,
              ram_mb: ramMb.trim() ? Number(ramMb) : undefined,
              cpus: cpus.trim() ? Number(cpus) : undefined,
              setup_level: setupLevel.trim() ? Number(setupLevel) : undefined,
            }),
      },
      {
        onSuccess: (env) => {
          const createdName = env?.name ?? name.trim()
          if (mode === 'recipe') {
            // No VM exists yet -- the disk is built on first `environment load`,
            // so the immediate-verify flow (below, baked-only) doesn't apply.
            toast.success('Recipe environment created', 'Load it to build the disk on first use.')
            onOpenChange(false)
            return
          }
          setVerifyState({ name: createdName, projectPath: submittedProjectPath })
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <>
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

          <FormField label="Type" htmlFor="env-mode">
            <select
              id="env-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as EnvironmentMode)}
              className={selectClassName}
            >
              <option value="baked">Baked (VM path)</option>
              <option value="recipe">Recipe</option>
            </select>
          </FormField>

          {mode === 'baked' && (
            <FormField label="VM path" htmlFor="env-vm-path" hint="Optional path to an existing VM">
              <Input
                id="env-vm-path"
                value={vmPath}
                onChange={(e) => setVmPath(e.target.value)}
                placeholder="/path/to/vm"
              />
            </FormField>
          )}

          {mode === 'recipe' && (
            <>
              <FormField label="OS profile" htmlFor="env-os-profile" required>
                <select
                  id="env-os-profile"
                  value={osProfile}
                  onChange={(e) => setOsProfile(e.target.value)}
                  className={selectClassName}
                >
                  <option value="">Select an OS profile…</option>
                  {osProfilesQuery.data?.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
              </FormField>

              <FormField
                label="ISO path"
                htmlFor="env-iso-path"
                required
                hint="Local ISO path on the analyst host"
              >
                <Input
                  id="env-iso-path"
                  value={isoPath}
                  onChange={(e) => setIsoPath(e.target.value)}
                  placeholder="/isos/ubuntu.iso"
                />
              </FormField>

              <div className="grid grid-cols-2 gap-4">
                <FormField label="Disk size" htmlFor="env-disk-size" hint="e.g. 40G">
                  <Input
                    id="env-disk-size"
                    value={diskSize}
                    onChange={(e) => setDiskSize(e.target.value)}
                    placeholder="40G"
                  />
                </FormField>

                <FormField label="RAM (MB)" htmlFor="env-ram-mb">
                  <Input
                    id="env-ram-mb"
                    type="number"
                    value={ramMb}
                    onChange={(e) => setRamMb(e.target.value)}
                    placeholder="4096"
                  />
                </FormField>

                <FormField label="CPUs" htmlFor="env-cpus">
                  <Input
                    id="env-cpus"
                    type="number"
                    value={cpus}
                    onChange={(e) => setCpus(e.target.value)}
                    placeholder="2"
                  />
                </FormField>

                <FormField
                  label="Setup level"
                  htmlFor="env-setup-level"
                  hint="0=bare 1=base 2=full 3=agent"
                >
                  <Input
                    id="env-setup-level"
                    type="number"
                    value={setupLevel}
                    onChange={(e) => setSetupLevel(e.target.value)}
                    placeholder="2"
                  />
                </FormField>
              </div>
            </>
          )}

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
    <VerifyEnvironmentDialog
      open={verifyState !== null}
      onOpenChange={(o) => {
        if (!o) setVerifyState(null)
      }}
      environmentName={verifyState?.name ?? null}
      projectPath={verifyState?.projectPath ?? null}
      onSkip={() => {
        if (verifyState) {
          toast.success('Environment created', verifyState.name)
        }
      }}
    />
    </>
  )
}
