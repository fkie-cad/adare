import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse, ExecuteActionRequest } from '@/types/api'
import type { ActionResult, ActionTypeMetadata } from '@/types/action'

export function useActionTypes() {
  return useQuery({
    queryKey: ['action-types'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<ActionTypeMetadata[]>>(endpoints.actionTypes)
      return data.data ?? []
    },
    staleTime: Infinity,
  })
}

export function useExecuteAction(sessionId: string) {
  return useMutation({
    mutationFn: async (request: ExecuteActionRequest) => {
      const { data } = await api.post<ApiResponse<ActionResult>>(endpoints.actionExecute(sessionId), request)
      return data.data!
    },
  })
}
