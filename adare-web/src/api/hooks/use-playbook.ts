import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse, SavePlaybookRequest } from '@/types/api'

export function useLoadPlaybook(name: string) {
  return useQuery({
    queryKey: ['playbook', name],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<string>>(endpoints.playbookLoad(name))
      return data.data ?? ''
    },
    enabled: !!name,
  })
}

export function useSavePlaybook() {
  return useMutation({
    mutationFn: async (request: SavePlaybookRequest) => {
      const { data } = await api.post<ApiResponse<string>>(endpoints.playbookSave, request)
      return data.data
    },
  })
}
