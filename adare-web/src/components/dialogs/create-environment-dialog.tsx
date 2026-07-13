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
import {
  useCreateEnvironment,
  useOsProfiles,
  useCheckEnvironmentUrl,
  type CheckUrlResult,
} from '@/api/hooks/use-environments'
import { useProjects } from '@/api/hooks/use-projects'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultProjectPath?: string
}

type EnvironmentMode = 'baked' | 'recipe'

const selectClassName =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'

// Mirrors the ADARE publish contract (server `check_file_validity`): a baked VM
// must be an http(s) disk image with a 64-hex sha256. The web variant only
// accepts published URLs so the environment it produces is always publishable.
const SHA256_RE = /^[0-9a-f]{64}$/
const BAKED_VM_EXTENSIONS = ['.ova', '.qcow2', '.vmdk', '.vdi', '.img']

function isHttpUrl(value: string): boolean {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

function hasDiskExtension(value: string): boolean {
  try {
    const path = new URL(value).pathname.toLowerCase()
    return BAKED_VM_EXTENSIONS.some((ext) => path.endsWith(ext))
  } catch {
    return false
  }
}

export function CreateEnvironmentDialog({ open, onOpenChange, defaultProjectPath }: Props) {
  const projectsQuery = useProjects()
  const osProfilesQuery = useOsProfiles()
  const [projectPath, setProjectPath] = useState(defaultProjectPath ?? '')
  const [name, setName] = useState('')
  const [mode, setMode] = useState<EnvironmentMode>('baked')
  const [vmUrl, setVmUrl] = useState('')
  const [vmSha256, setVmSha256] = useState('')
  const [osProfile, setOsProfile] = useState('')
  const [isoUrl, setIsoUrl] = useState('')
  const [isoSha256, setIsoSha256] = useState('')
  const [diskSize, setDiskSize] = useState('')
  const [ramMb, setRamMb] = useState('')
  const [cpus, setCpus] = useState('')
  const [setupLevel, setSetupLevel] = useState('')
  const [urlCheck, setUrlCheck] = useState<CheckUrlResult | null>(null)
  const mutation = useCreateEnvironment()
  const checkMutation = useCheckEnvironmentUrl()

  useEffect(() => {
    if (!open) {
      setName('')
      setMode('baked')
      setVmUrl('')
      setVmSha256('')
      setOsProfile('')
      setIsoUrl('')
      setIsoSha256('')
      setDiskSize('')
      setRamMb('')
      setCpus('')
      setSetupLevel('')
      setUrlCheck(null)
      mutation.reset()
      checkMutation.reset()
      setProjectPath(defaultProjectPath ?? '')
    }
  }, [open, defaultProjectPath, mutation, checkMutation])

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

  // A prior reachability result is stale once the source URL/sha or mode changes.
  useEffect(() => {
    setUrlCheck(null)
    checkMutation.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vmUrl, vmSha256, isoUrl, isoSha256, mode])

  // --- Client-side format validation (mirrors the publish contract) ---
  const vmUrlTrimmed = vmUrl.trim()
  const vmSha256Trimmed = vmSha256.trim()
  const isoUrlTrimmed = isoUrl.trim()
  const isoSha256Trimmed = isoSha256.trim()

  const vmUrlError =
    vmUrlTrimmed.length === 0
      ? null
      : !isHttpUrl(vmUrlTrimmed)
        ? 'Must be an http(s) URL.'
        : !hasDiskExtension(vmUrlTrimmed)
          ? `Must point to a disk image (${BAKED_VM_EXTENSIONS.join(', ')}).`
          : null
  const vmSha256Error =
    vmSha256Trimmed.length === 0
      ? null
      : !SHA256_RE.test(vmSha256Trimmed)
        ? 'Must be 64 lowercase hex characters.'
        : null
  const isoUrlError =
    isoUrlTrimmed.length === 0 ? null : !isHttpUrl(isoUrlTrimmed) ? 'Must be an http(s) URL.' : null
  const isoSha256Error =
    isoSha256Trimmed.length === 0
      ? null
      : !SHA256_RE.test(isoSha256Trimmed)
        ? 'Must be 64 lowercase hex characters.'
        : null

  const bakedValid =
    isHttpUrl(vmUrlTrimmed) && hasDiskExtension(vmUrlTrimmed) && SHA256_RE.test(vmSha256Trimmed)
  const recipeValid =
    osProfile.trim().length > 0 && isHttpUrl(isoUrlTrimmed) && SHA256_RE.test(isoSha256Trimmed)

  const canSubmit =
    projectPath.trim().length > 0 &&
    name.trim().length > 0 &&
    !mutation.isPending &&
    (mode === 'baked' ? bakedValid : recipeValid)

  // --- URL reachability probe (proxied through the backend HEAD check) ---
  const activeUrl = mode === 'baked' ? vmUrlTrimmed : isoUrlTrimmed
  const activeSha = mode === 'baked' ? vmSha256Trimmed : isoSha256Trimmed
  const activeUrlValid =
    mode === 'baked' ? isHttpUrl(vmUrlTrimmed) && hasDiskExtension(vmUrlTrimmed) : isHttpUrl(isoUrlTrimmed)

  const handleCheckUrl = () => {
    if (!activeUrl || !activeUrlValid) return
    checkMutation.mutate(
      { url: activeUrl, sha256: activeSha || undefined, kind: mode === 'baked' ? 'vm' : 'iso' },
      { onSuccess: (result) => setUrlCheck(result) },
    )
  }

  const renderUrlCheck = () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleCheckUrl}
        disabled={!activeUrl || !activeUrlValid || checkMutation.isPending}
      >
        {checkMutation.isPending && <Spinner className="h-4 w-4" />}
        Check URL
      </Button>
      {checkMutation.isError && (
        <span className="text-xs text-destructive">Reachability check failed. Try again.</span>
      )}
      {urlCheck &&
        (urlCheck.reachable ? (
          <span className="text-xs text-green-600 dark:text-green-500">
            Reachable{urlCheck.status ? ` (HTTP ${urlCheck.status})` : ''}
          </span>
        ) : (
          <span className="text-xs text-amber-600 dark:text-amber-500">
            {urlCheck.reason ?? 'Not reachable.'}
          </span>
        ))}
    </div>
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    const submittedProjectPath = projectPath.trim()
    mutation.mutate(
      {
        project_path: submittedProjectPath,
        name: name.trim(),
        ...(mode === 'baked'
          ? { vm_url: vmUrlTrimmed, vm_sha256: vmSha256Trimmed }
          : {
              os_profile: osProfile,
              iso_url: isoUrlTrimmed,
              iso_sha256: isoSha256Trimmed,
              disk_size: diskSize.trim() || undefined,
              ram_mb: ramMb.trim() ? Number(ramMb) : undefined,
              cpus: cpus.trim() ? Number(cpus) : undefined,
              setup_level: setupLevel.trim() ? Number(setupLevel) : undefined,
            }),
      },
      {
        onSuccess: () => {
          // Both shapes are descriptor-only: the disk is downloaded (baked URL)
          // or built (recipe) on the first `environment load`, so there is no
          // VM to verify at create time.
          toast.success(
            mode === 'baked' ? 'Baked-URL environment created' : 'Recipe environment created',
            'Load it to download/build the disk on first use.',
          )
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
            <DialogDescription>
              Define an environment from a published (hosted) VM disk or installer ISO URL.
            </DialogDescription>
          </DialogHeader>

          <FormField label="Project" htmlFor="env-project" required>
            <select
              id="env-project"
              value={projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              className={selectClassName}
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
              <option value="baked">Baked (published VM URL)</option>
              <option value="recipe">Recipe (published ISO URL)</option>
            </select>
          </FormField>

          {mode === 'baked' && (
            <>
              <FormField
                label="VM URL"
                htmlFor="env-vm-url"
                required
                error={vmUrlError ?? undefined}
                hint="Published http(s) disk image (.ova, .qcow2, .vmdk, .vdi, .img)"
              >
                <Input
                  id="env-vm-url"
                  value={vmUrl}
                  onChange={(e) => setVmUrl(e.target.value)}
                  onBlur={() => {
                    if (!urlCheck && activeUrlValid) handleCheckUrl()
                  }}
                  placeholder="https://host.example/disks/ubuntu24.qcow2"
                />
              </FormField>

              <FormField
                label="VM sha256"
                htmlFor="env-vm-sha256"
                required
                error={vmSha256Error ?? undefined}
                hint="Expected SHA256 of the hosted disk (64 hex chars)"
              >
                <Input
                  id="env-vm-sha256"
                  value={vmSha256}
                  onChange={(e) => setVmSha256(e.target.value)}
                  placeholder="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                />
              </FormField>

              {renderUrlCheck()}
            </>
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
                label="ISO URL"
                htmlFor="env-iso-url"
                required
                error={isoUrlError ?? undefined}
                hint="Published http(s) installer ISO"
              >
                <Input
                  id="env-iso-url"
                  value={isoUrl}
                  onChange={(e) => setIsoUrl(e.target.value)}
                  onBlur={() => {
                    if (!urlCheck && activeUrlValid) handleCheckUrl()
                  }}
                  placeholder="https://host.example/isos/ubuntu-24.04.iso"
                />
              </FormField>

              <FormField
                label="ISO sha256"
                htmlFor="env-iso-sha256"
                required
                error={isoSha256Error ?? undefined}
                hint="Expected SHA256 of the hosted ISO (64 hex chars)"
              >
                <Input
                  id="env-iso-sha256"
                  value={isoSha256}
                  onChange={(e) => setIsoSha256(e.target.value)}
                  placeholder="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                />
              </FormField>

              {renderUrlCheck()}

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
                    min={0}
                    max={3}
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
  )
}
