import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

/**
 * Hooks for managing locally-registered VMs (database-tracked) and for
 * resolving a running VM's live VirtualSpice display URL (watch / embed).
 */

// A locally-registered VM: a row of GET /api/local-vms (VmListItem) or, with
// the detail-only fields, GET /api/local-vms/{id} (VmInfo).
export interface LocalVm {
  id: string
  name?: string
  description?: string
  hypervisor?: string
  os_platform?: string | null
  instance_count?: number
  file_hash?: string
  /** List rows: the VM disk/image file. */
  path?: string
  /** Detail only: the VM disk/image file. */
  file_path?: string
  [key: string]: unknown
}

export function useLocalVms() {
  return useQuery({
    queryKey: ['local-vms'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<LocalVm[]>>(endpoints.localVms)
      return data.data ?? []
    },
  })
}

export function useLocalVm(vmId: string) {
  return useQuery({
    queryKey: ['local-vm', vmId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<LocalVm>>(endpoints.localVm(vmId))
      return data.data!
    },
    enabled: !!vmId,
  })
}

export function useDeleteLocalVm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ vmId, force = false }: { vmId: string; force?: boolean }) => {
      await api.delete(`${endpoints.localVm(vmId)}?force=${force}`)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['local-vms'] }),
  })
}

/** A running VM instance (as opposed to a registered VM image). */
export interface VmInstance {
  id: string
  vm_id?: string
  vm_name?: string
  /** Hypervisor domain name (what the live view resolves), unique per instance. */
  instance_name?: string
  status?: 'active' | 'available' | 'stopped' | string
  websocket_port?: number
  hypervisor?: string
  /** ULID of the run holding this instance (an experiment run or a dev session), if any. */
  current_experiment_run_id?: string | null
  [key: string]: unknown
}

export interface VmSnapshot {
  name: string
  instance_id?: string
  [key: string]: unknown
}

export interface VmInstanceUsage {
  [key: string]: unknown
}

export function useVmInstances(vmId?: string) {
  return useQuery({
    queryKey: ['vm-instances', vmId ?? null],
    queryFn: async () => {
      const url = vmId
        ? `${endpoints.vmInstances}?vm_id=${encodeURIComponent(vmId)}`
        : endpoints.vmInstances
      const { data } = await api.get<ApiResponse<VmInstance[]>>(url)
      return data.data ?? []
    },
  })
}

/** Instances that are running right now (status `active`), refreshed every few seconds. */
export function useRunningVmInstances() {
  return useQuery({
    queryKey: ['vm-instances', null],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<VmInstance[]>>(endpoints.vmInstances)
      return data.data ?? []
    },
    select: (instances) => instances.filter((i) => i.status === 'active'),
    refetchInterval: 5000,
  })
}

/** A log file a running instance can be tailed through (GET /api/vm-instances/{id}/logs). */
export interface VmInstanceLogSource {
  /** `run/<file>` for the run's logs, `libvirt` for the hypervisor's domain log. */
  key: string
  name: string
  size: number
}

export function useVmInstanceLogs(instanceId: string | undefined) {
  return useQuery({
    queryKey: ['vm-instance-logs', instanceId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<VmInstanceLogSource[]>>(
        endpoints.vmInstanceLogs(instanceId!),
      )
      return data.data ?? []
    },
    enabled: !!instanceId,
    // Logs appear as a run progresses (the agent log only once the guest is up).
    refetchInterval: 5000,
  })
}

/** One read of a log (GET /api/vm-instances/{id}/logs/{key}?offset=). */
export interface VmInstanceLogChunk {
  text: string
  offset: number
  next_offset: number
  size: number
  /** The file got shorter than the requested offset: drop what is shown. */
  reset: boolean
}

export async function fetchVmInstanceLogChunk(
  instanceId: string,
  key: string,
  offset: number | null,
): Promise<VmInstanceLogChunk> {
  const { data } = await api.get<ApiResponse<VmInstanceLogChunk>>(
    endpoints.vmInstanceLog(instanceId, key),
    { params: offset === null ? {} : { offset } },
  )
  return data.data!
}

export function useVmInstance(instanceId: string) {
  return useQuery({
    queryKey: ['vm-instance', instanceId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<VmInstance>>(endpoints.vmInstance(instanceId))
      return data.data!
    },
    enabled: !!instanceId,
  })
}

export function useVmInstanceUsage() {
  return useQuery({
    queryKey: ['vm-instance-usage'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<VmInstanceUsage>>(endpoints.vmInstanceUsage)
      return data.data!
    },
  })
}

export function useRemoveVmInstance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (instanceId: string) => {
      await api.delete(endpoints.vmInstance(instanceId))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vm-instances'] }),
  })
}

/** Result of DELETE /api/vm-instances (VmInstanceCleanupResult). */
export interface VmInstanceCleanupResult {
  removed_count: number
  removed_instances: string[]
  failed_count: number
  failed_instances: string[]
}

export function useRemoveAllStoppedInstances() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.delete<ApiResponse<VmInstanceCleanupResult>>(endpoints.vmInstances)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vm-instances'] }),
  })
}

export function useVmSnapshots(instanceId: string) {
  return useQuery({
    queryKey: ['vm-snapshots', instanceId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<VmSnapshot[]>>(endpoints.vmInstanceSnapshots(instanceId))
      return data.data ?? []
    },
    enabled: !!instanceId,
  })
}

export function useDeleteVmSnapshot(instanceId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      await api.delete(endpoints.vmInstanceSnapshotDelete(instanceId, name))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vm-snapshots', instanceId] }),
  })
}

/**
 * Live-display connection info for a running VM, as resolved by the backend.
 *
 * The backend maps the ADARE VM *name* to VirtualSpice's *uuid* and returns the
 * same-origin WebSocket path (`ws_path`) that the ADARE-owned viewer connects
 * to. ADARE proxies that socket to VirtualSpice internally, so the browser
 * never contacts `:8081` directly (no cross-origin, no mixed-content).
 */
export interface VmSpiceInfo {
  uuid: string
  name: string
  view_only: boolean
  spice_port: number
  ws_path: string
}

/**
 * Build the same-origin WebSocket URL for the viewer from a resolved `ws_path`.
 */
export function buildVmWsUrl(wsPath: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${wsPath}`
}

/**
 * Resolve a running VM's live display connection info.
 *
 * @returns the {@link VmSpiceInfo}, or `null` if the VM could not be resolved
 *          (VirtualSpice down or no matching running domain).
 */
export async function resolveVmSpice(
  name: string,
  viewOnly = true,
): Promise<VmSpiceInfo | null> {
  const response = await fetch(endpoints.vmWatchUrl(name, viewOnly))
  if (!response.ok) {
    return null
  }
  return (await response.json()) as VmSpiceInfo
}

/**
 * React-Query hook exposing a running VM's live display connection info for the
 * in-app viewer. `data === null` means "not reachable" (VirtualSpice down or VM
 * stopped) — distinct from `isLoading`. Does not retry (a 404 is a definitive
 * "no such running VM", not a transient failure).
 */
export function useVmSpice(name: string, viewOnly = true, enabled = true) {
  return useQuery({
    queryKey: ['vm-spice', name, viewOnly],
    queryFn: () => resolveVmSpice(name, viewOnly),
    enabled: enabled && !!name,
    retry: false,
    staleTime: 60_000,
  })
}
