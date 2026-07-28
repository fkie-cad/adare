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

// Where a recipe environment's installer ISO comes from. 'url' is a published
// http(s) ISO the framework downloads itself; 'byo' declares only a filename +
// digest and leaves the consumer to supply the file locally. BYO exists because
// a Microsoft Windows ISO cannot legally be rehosted, so it is offered for
// Windows OS profiles only (the server rejects it otherwise with
// `ByoIsoRequiresWindowsProfile`).
type IsoSource = 'url' | 'byo'

const selectClassName =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'

// Mirrors the ADARE publish contract (server `check_file_validity`): a baked VM
// must be an http(s) URL with a 64-hex sha256. Any host is accepted (owncloud /
// Nextcloud share links included), so the disk format is chosen explicitly
// rather than inferred from a file extension.
const SHA256_RE = /^[0-9a-f]{64}$/
const VM_FORMATS = ['qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw'] as const

// Mirrors `ISO_NAME_RE` in `adare/adare/adare/services/recipe_contract.py` and the
// server's `giteaeventmanager/action/environment_contract.py`. A BYO ISO is a bare
// filename that the consumer resolves against their own local ISO directory, so it
// must not be able to escape it: no path separators, no `..`, no leading dot, and a
// literal `.iso` suffix. This regex is a hand-maintained third copy of the same
// rule — divergence between the three is a known bug class, so change all three
// together (a name this copy accepts but the server rejects fails at create time;
// one this copy rejects but the server accepts is silently unreachable from the UI).
const ISO_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.iso$/

function isHttpUrl(value: string): boolean {
  try {
    const u = new URL(value)
    return u.protocol === 'http:' || u.protocol === 'https:'
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
  const [vmFormat, setVmFormat] = useState<string>('qcow2')
  const [osProfile, setOsProfile] = useState('')
  const [isoSource, setIsoSource] = useState<IsoSource>('url')
  const [isoUrl, setIsoUrl] = useState('')
  const [isoName, setIsoName] = useState('')
  const [isoNotes, setIsoNotes] = useState('')
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
      setVmFormat('qcow2')
      setOsProfile('')
      setIsoSource('url')
      setIsoUrl('')
      setIsoName('')
      setIsoNotes('')
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

  // The catalog entry behind the selected profile (if the query has loaded). Its
  // `platform` is what decides whether BYO ISO is offered at all.
  const selectedProfile = osProfilesQuery.data?.find((p) => p.name === osProfile)
  const isWindowsProfile = selectedProfile?.platform === 'windows'

  // A Windows -> Linux switch must not leave `isoSource` on 'byo': the BYO control
  // is hidden for non-Windows profiles, so a stale 'byo' would submit an `iso_name`
  // the server rejects with `ByoIsoRequiresWindowsProfile`, against a form that no
  // longer shows the offending field. Reset on every profile change.
  useEffect(() => {
    setIsoSource('url')
  }, [osProfile])

  // Prefill whatever the catalog knows about this profile's ISO. The three fields
  // are independent: a Linux profile publishes a URL (+ digest), a Windows profile
  // publishes no URL at all — that ISO cannot legally be rehosted, which is the whole
  // reason BYO exists — but does publish `iso_notes`, the download pointer, so the
  // publisher does not have to retype it. Empty/absent values prefill nothing, and a
  // value the user already typed is never clobbered.
  useEffect(() => {
    const catalogUrl = selectedProfile?.iso_url ?? ''
    if (catalogUrl) setIsoUrl((current) => (current.trim().length > 0 ? current : catalogUrl))
    const catalogSha = selectedProfile?.iso_sha256 ?? ''
    if (catalogSha) setIsoSha256((current) => (current.trim().length > 0 ? current : catalogSha))
    const catalogNotes = selectedProfile?.iso_notes ?? ''
    if (catalogNotes) setIsoNotes((current) => (current.trim().length > 0 ? current : catalogNotes))
  }, [selectedProfile])

  // A prior reachability result is stale once the source URL/sha or mode changes.
  useEffect(() => {
    setUrlCheck(null)
    checkMutation.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vmUrl, vmSha256, isoUrl, isoSha256, mode, isoSource])

  // --- Client-side format validation (mirrors the publish contract) ---
  const vmUrlTrimmed = vmUrl.trim()
  const vmSha256Trimmed = vmSha256.trim()
  const isoUrlTrimmed = isoUrl.trim()
  const isoNameTrimmed = isoName.trim()
  const isoSha256Trimmed = isoSha256.trim()

  const vmUrlError =
    vmUrlTrimmed.length === 0
      ? null
      : !isHttpUrl(vmUrlTrimmed)
        ? 'Must be an http(s) URL.'
        : null
  const vmSha256Error =
    vmSha256Trimmed.length === 0
      ? null
      : !SHA256_RE.test(vmSha256Trimmed)
        ? 'Must be 64 lowercase hex characters.'
        : null
  const isoUrlError =
    isoUrlTrimmed.length === 0 ? null : !isHttpUrl(isoUrlTrimmed) ? 'Must be an http(s) URL.' : null
  const isoNameError =
    isoNameTrimmed.length === 0
      ? null
      : !ISO_NAME_RE.test(isoNameTrimmed)
        ? 'Must be a bare file name ending in .iso: no path separators, no "..", no leading dot, at most 200 characters. It is resolved inside the consumer\'s own ISO directory, so anything that could point outside it is rejected.'
        : null
  const isoSha256Error =
    isoSha256Trimmed.length === 0
      ? null
      : !SHA256_RE.test(isoSha256Trimmed)
        ? 'Must be 64 lowercase hex characters.'
        : null

  const bakedValid =
    isHttpUrl(vmUrlTrimmed) &&
    SHA256_RE.test(vmSha256Trimmed) &&
    (VM_FORMATS as readonly string[]).includes(vmFormat)
  // BYO is only reachable for a Windows profile: the control is hidden otherwise and
  // `isoSource` resets on every profile change. Effects run after render though, so
  // clamp the source here too — that way a single render with a stale 'byo' can never
  // gate submit on, or submit, a field the server would refuse.
  const isoSourceEffective: IsoSource = isWindowsProfile ? isoSource : 'url'
  const recipeValid =
    osProfile.trim().length > 0 &&
    SHA256_RE.test(isoSha256Trimmed) &&
    (isoSourceEffective === 'url' ? isHttpUrl(isoUrlTrimmed) : ISO_NAME_RE.test(isoNameTrimmed))

  const canSubmit =
    projectPath.trim().length > 0 &&
    name.trim().length > 0 &&
    !mutation.isPending &&
    (mode === 'baked' ? bakedValid : recipeValid)

  // --- URL reachability probe (proxied through the backend HEAD check) ---
  const activeUrl = mode === 'baked' ? vmUrlTrimmed : isoUrlTrimmed
  const activeSha = mode === 'baked' ? vmSha256Trimmed : isoSha256Trimmed
  // In BYO mode there is no URL to HEAD, so the probe stays disabled (and its UI is
  // not rendered at all).
  const activeUrlValid =
    mode === 'baked'
      ? isHttpUrl(vmUrlTrimmed)
      : isoSourceEffective === 'url' && isHttpUrl(isoUrlTrimmed)

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
          ? { vm_url: vmUrlTrimmed, vm_sha256: vmSha256Trimmed, vm_format: vmFormat }
          : {
              os_profile: osProfile,
              // Exactly one of `iso_url` / `iso_name` — the unused one is omitted
              // rather than sent as an empty string (the server rejects both-or-
              // neither), the same way the optional params below drop out when blank.
              ...(isoSourceEffective === 'url'
                ? { iso_url: isoUrlTrimmed }
                : { iso_name: isoNameTrimmed, iso_notes: isoNotes.trim() || undefined }),
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
              <option value="recipe">Recipe (installer ISO)</option>
            </select>
          </FormField>

          {mode === 'baked' && (
            <>
              <FormField
                label="VM URL"
                htmlFor="env-vm-url"
                required
                error={vmUrlError ?? undefined}
                hint="Any published http(s) URL (owncloud/Nextcloud share links work). Pick the disk format below."
              >
                <Input
                  id="env-vm-url"
                  value={vmUrl}
                  onChange={(e) => setVmUrl(e.target.value)}
                  onBlur={() => {
                    if (!urlCheck && activeUrlValid) handleCheckUrl()
                  }}
                  placeholder="https://cloud.example/s/TOKEN/download"
                />
              </FormField>

              <FormField
                label="Disk format"
                htmlFor="env-vm-format"
                required
                hint="Format of the hosted disk image"
              >
                <select
                  id="env-vm-format"
                  value={vmFormat}
                  onChange={(e) => setVmFormat(e.target.value)}
                  className={selectClassName}
                >
                  {VM_FORMATS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
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

              {isWindowsProfile && (
                <FormField
                  label="ISO source"
                  htmlFor="env-iso-source"
                  hint="A Windows ISO cannot be rehosted, so it may instead be named for the consumer to supply locally."
                >
                  <select
                    id="env-iso-source"
                    value={isoSource}
                    onChange={(e) => setIsoSource(e.target.value as IsoSource)}
                    className={selectClassName}
                  >
                    <option value="url">Published URL</option>
                    <option value="byo">Consumer supplies the ISO</option>
                  </select>
                </FormField>
              )}

              {isoSourceEffective === 'url' ? (
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
              ) : (
                <FormField
                  label="ISO file name"
                  htmlFor="env-iso-name"
                  required
                  error={isoNameError ?? undefined}
                  hint="Bare file name of the ISO the consumer places in their own ISO directory"
                >
                  <Input
                    id="env-iso-name"
                    value={isoName}
                    onChange={(e) => setIsoName(e.target.value)}
                    placeholder="Win11_24H2_English_arm64.iso"
                  />
                </FormField>
              )}

              <FormField
                label="ISO sha256"
                htmlFor="env-iso-sha256"
                required
                error={isoSha256Error ?? undefined}
                hint={
                  isoSourceEffective === 'url'
                    ? 'Expected SHA256 of the hosted ISO (64 lowercase hex chars)'
                    : 'Expected SHA256 of the ISO the consumer supplies — this is what pins the exact file (64 lowercase hex chars)'
                }
              >
                <Input
                  id="env-iso-sha256"
                  value={isoSha256}
                  onChange={(e) => setIsoSha256(e.target.value)}
                  placeholder="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                />
              </FormField>

              {/* No URL to HEAD in BYO mode, so the reachability probe is not
                  rendered at all rather than shown disabled. */}
              {isoSourceEffective === 'url' ? (
                renderUrlCheck()
              ) : (
                <FormField
                  label="Download notes"
                  htmlFor="env-iso-notes"
                  hint="Optional plain text pointing the consumer at this exact ISO. Prefilled from the OS profile where the catalog has a pointer; stored and shown verbatim, never as markup."
                >
                  <Textarea
                    id="env-iso-notes"
                    value={isoNotes}
                    onChange={(e) => setIsoNotes(e.target.value)}
                    placeholder={
                      'Microsoft Software Download: Windows 11 arm64\nEdition: Windows 11 (multi-edition), English (United States)'
                    }
                  />
                </FormField>
              )}

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
