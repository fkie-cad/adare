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
