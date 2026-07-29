import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

/**
 * Hooks for managing locally-registered VMs (database-tracked) and for
 * resolving a running VM's live VirtualSpice display URL (watch / embed).
 */

// Shape of a locally-registered VM record. The backend returns whatever
// `AdareAPI().vm` yields — we keep this permissive and let callers narrow.
export interface LocalVm {
  id: string
  name?: string
  path?: string
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
  name?: string
  status?: 'active' | 'available' | 'stopped' | string
  websocket_port?: number
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

export function useRemoveAllStoppedInstances() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.delete<ApiResponse<number>>(endpoints.vmInstances)
      return data.data ?? 0
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
