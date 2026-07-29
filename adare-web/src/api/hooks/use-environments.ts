import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'
import { assertOk, unwrap, unwrapOr } from '@/types/api'

export interface RecipeInfo {
  profile: string
  iso: string
  iso_sha256: string
  template?: string
  setup_level: number
  disk_size?: string
  ram_mb?: number
  cpus?: number
  arch?: string
}

export interface Environment {
  name: string
  project_path?: string
  vm?: string
  vm_type?: string
  vm_sha256?: string
  // Optional install-profile provenance for a baked source (informational
  // only -- see CreateEnvironmentRequest.source_profile).
  source_profile?: string
  source_iso_sha256?: string
  recipe?: RecipeInfo | null
  [key: string]: unknown
}

export interface CreateEnvironmentRequest {
  project_path: string
  name: string
  // Baked source: a published disk-image URL + its sha256 + disk format
  // (web = remote-only; any http(s) host, format chosen explicitly).
  vm_url?: string
  vm_sha256?: string
  vm_format?: string
  // Optional install-profile provenance for a baked source: which OS profile
  // the disk was built from, and (if still known) the source ISO's sha256.
  // Informational only -- never validated, never required.
  source_profile?: string
  source_iso_sha256?: string
  // Recipe source: OS profile + the installer ISO + its sha256, plus params.
  // Exactly one of `iso_url` (published http(s) ISO) or `iso_name` (BYO: a bare
  // filename the consumer supplies locally, Windows profiles only) is sent;
  // `iso_notes` is an optional plain-text download pointer for a BYO ISO.
  os_profile?: string
  iso_url?: string
  iso_name?: string | null
  iso_notes?: string | null
  iso_sha256?: string
  disk_size?: string
  ram_mb?: number
  cpus?: number
  arch?: string
  setup_level?: number
}

export interface CheckUrlRequest {
  url: string
  sha256?: string
  kind: 'vm' | 'iso'
}

export interface CheckUrlResult {
  valid: boolean
  reachable: boolean
  status: number | null
  reason: string | null
}

export interface OsProfile {
  name: string
  display_name: string
  platform: string
  distribution: string
  version: string
  architecture: string
  default_disk_size: string
  default_ram_mb: number
  default_cpus: number
  // The catalog's canonical ISO for this profile, used to prefill the
  // create-environment form. Optional: older servers omit them entirely, newer
  // ones may return empty strings. A Windows profile has no `iso_url` (that ISO
  // cannot legally be rehosted — see the BYO ISO flow) but does carry
  // `iso_notes`, the download pointer telling a consumer where to get it.
  iso_url?: string
  iso_sha256?: string
  iso_notes?: string
}

export interface VerifyEnvironmentRequest {
  name: string
  project_path: string
}

export interface VerifyEnvironmentResponse {
  run_ulid: string
  experiment_name: string
}

// Every hook below unwraps its response through `types/api`'s helpers. The webapi
// signals a rejection as HTTP **200** with `{success: false, error: {...}}`
// (`result_to_response` in adare/adare/webapi/adapters.py), so axios resolves and
// the interceptor in `api/client.ts` never sees it. Reading `data.data!` or
// `data.data ?? []` therefore turned a server-side failure into either a silent
// success or a convincing empty list. The one exception is
// `useCheckEnvironmentUrl`: that route answers `{"success": True}` on all three of
// its paths and encodes validity inside `data.valid` / `reachable` / `reason`, so
// there is nothing to unwrap.
export function useEnvironments() {
  return useQuery({
    queryKey: ['environments'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Environment[]>>(endpoints.environments)
      return unwrapOr(data, 'Failed to load environments.', [])
    },
  })
}

export function useEnvironment(name: string) {
  return useQuery({
    queryKey: ['environment', name],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Environment>>(endpoints.environment(name))
      return unwrap(data, `Failed to load environment "${name}".`)
    },
    enabled: !!name,
  })
}

export function useOsProfiles() {
  return useQuery({
    queryKey: ['os-profiles'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<OsProfile[]>>(endpoints.osProfiles)
      return unwrapOr(data, 'Failed to load OS profiles.', [])
    },
  })
}

// A rejected create (`AmbiguousIsoSource`, `MissingOsProfile`,
// `UnknownOsProfileError`, `ByoIsoRequiresWindowsProfile`, `InvalidIsoName`,
// `InvalidIsoUrl`, `InvalidVmUrl`) is the reason `unwrap` exists: without it the
// dialog fired its success toast and closed, and the reason was never shown.
export function useCreateEnvironment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateEnvironmentRequest) => {
      const { data } = await api.post<ApiResponse<Environment>>(endpoints.environments, request)
      return unwrap(data, 'Failed to create environment.')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['environments'] }),
  })
}

// Not unwrapped, deliberately: `POST /api/environments/check-url` answers
// `{"success": True}` on all three of its paths and puts the verdict in
// `data.valid` / `reachable` / `reason`, so an unreachable URL is a *result* here,
// not a rejection.
export function useCheckEnvironmentUrl() {
  return useMutation({
    mutationFn: async (request: CheckUrlRequest) => {
      const { data } = await api.post<ApiResponse<CheckUrlResult>>(
        endpoints.environmentCheckUrl,
        request,
      )
      return data.data!
    },
  })
}

export function useVerifyEnvironment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: VerifyEnvironmentRequest) => {
      const { data } = await api.post<ApiResponse<VerifyEnvironmentResponse>>(
        endpoints.verifyEnvironment(request.name),
        { project_path: request.project_path },
      )
      return unwrap(data, `Failed to start verification of "${request.name}".`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}

export function useDeleteEnvironment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, force = false }: { name: string; force?: boolean }) => {
      // The body was previously discarded entirely, so a refused delete (in use by
      // an experiment, needs --force) reported success and the row vanished from
      // the list until the next refetch put it back.
      const { data } = await api.delete<ApiResponse<unknown>>(
        endpoints.environmentDelete(name, force),
      )
      assertOk(data, `Failed to delete environment "${name}".`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['environments'] }),
  })
}
