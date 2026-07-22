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
  viewOnly = false,
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
export function useVmSpice(name: string, viewOnly = false, enabled = true) {
  return useQuery({
    queryKey: ['vm-spice', name, viewOnly],
    queryFn: () => resolveVmSpice(name, viewOnly),
    enabled: enabled && !!name,
    retry: false,
    staleTime: 60_000,
  })
}
