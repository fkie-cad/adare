import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

/**
 * Hooks for managing locally-registered VMs (database-tracked).
 *
 * For interacting with running VMs (VirtualSpice instances, snapshots,
 * live events), use the VM proxy paths from `endpoints.vmProxy` /
 * `endpoints.vmWebSocket` / `endpoints.vmEventsWebSocket` directly, since
 * those requests hit the FastAPI reverse proxy mounted at the app root
 * (outside the `/api` axios baseURL).
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
 * Call an arbitrary VirtualSpice REST endpoint via the backend proxy.
 *
 * VirtualSpice routes are proxied at `/api/vm/{path}` from the FastAPI root,
 * so this helper uses `fetch` directly rather than the `/api`-scoped axios
 * instance to avoid double-prefixing.
 */
export async function callVmProxy<T = unknown>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(endpoints.vmProxy(path), init)
  if (!response.ok) {
    throw new Error(`VM proxy request failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

/**
 * Open a running VM's live screen in a new tab via VirtualSpice
 * (launch-and-hand-off — no embedded viewer).
 *
 * Resolves the ADARE VM *name* to VirtualSpice's *uuid* through the backend,
 * then opens VirtualSpice's own standalone display page directly on `:8081`
 * (same-origin with its spice-client). Read-only by default; the observer can
 * still toggle control from VirtualSpice's own toolbar.
 *
 * @returns `true` if a tab was opened, `false` if the VM could not be resolved
 *          (VirtualSpice down or no matching running domain).
 */
export async function openVmWatch(name: string, viewOnly = true): Promise<boolean> {
  const response = await fetch(endpoints.vmWatchUrl(name, viewOnly))
  if (!response.ok) {
    return false
  }
  const { path, spice_port } = (await response.json()) as {
    path: string
    spice_port: number
  }
  window.open(`http://${location.hostname}:${spice_port}${path}`, '_blank')
  return true
}
