import { useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'

export interface RunAgentRequest {
  goal: string
  max_steps?: number
  stall_limit?: number
  planning?: boolean
  grounding?: boolean
  video?: boolean
}

export interface RunAgentResponse {
  started: boolean
}

export function useRunAgent(sessionId: string) {
  return useMutation({
    mutationFn: async (request: RunAgentRequest) => {
      const { data } = await api.post<RunAgentResponse>(
        endpoints.agentRun(sessionId),
        request,
      )
      return data
    },
  })
}
