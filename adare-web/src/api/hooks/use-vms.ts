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
 * Resolve a running VM's live VirtualSpice display URL.
 *
 * Resolves the ADARE VM *name* to VirtualSpice's *uuid* through the backend,
 * then builds the absolute URL to VirtualSpice's own standalone display page
 * on `:8081` (same-origin with its spice-client). This single URL is consumed
 * both by the pop-out tab (`openVmWatch`) and the in-app `<iframe>` embed
 * (`VmLiveView` / `useVmWatchUrl`).
 *
 * @returns the absolute `display.html` URL, or `null` if the VM could not be
 *          resolved (VirtualSpice down or no matching running domain).
 */
export async function resolveVmWatchUrl(
  name: string,
  viewOnly = true,
): Promise<string | null> {
  const response = await fetch(endpoints.vmWatchUrl(name, viewOnly))
  if (!response.ok) {
    return null
  }
  const { path, spice_port } = (await response.json()) as {
    path: string
    spice_port: number
  }
  return `http://${location.hostname}:${spice_port}${path}`
}

/**
 * Open a running VM's live screen in a new tab via VirtualSpice
 * (launch-and-hand-off — no embedded viewer). Used by the CLI-style
 * "pop out to tab" action.
 *
 * @returns `true` if a tab was opened, `false` if the VM could not be resolved.
 */
export async function openVmWatch(name: string, viewOnly = true): Promise<boolean> {
  const url = await resolveVmWatchUrl(name, viewOnly)
  if (!url) {
    return false
  }
  window.open(url, '_blank')
  return true
}

/**
 * React-Query hook exposing a running VM's live display URL for the in-app
 * embed. `data === null` means "not reachable" (VirtualSpice down or VM
 * stopped) — distinct from `isLoading`. Does not retry (a 404 is a definitive
 * "no such running VM", not a transient failure).
 */
export function useVmWatchUrl(name: string, viewOnly = false, enabled = true) {
  return useQuery({
    queryKey: ['vm-watch-url', name, viewOnly],
    queryFn: () => resolveVmWatchUrl(name, viewOnly),
    enabled: enabled && !!name,
    retry: false,
    staleTime: 60_000,
  })
}
