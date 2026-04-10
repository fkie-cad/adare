import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'
import type { DevSessionListItem, DevSessionInfo, SessionState, StartSessionRequest } from '@/types/session'

export function useSessions() {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<DevSessionListItem[]>>(endpoints.sessions)
      return data.data ?? []
    },
    refetchInterval: 10_000,
  })
}

export function useSessionState(sessionId: string) {
  return useQuery({
    queryKey: ['session-state', sessionId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<SessionState>>(endpoints.sessionState(sessionId))
      return data.data!
    },
    enabled: !!sessionId,
  })
}

export function useStartSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: StartSessionRequest) => {
      const { data } = await api.post<ApiResponse<DevSessionInfo>>(endpoints.sessionStart, request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
}

export function useStopSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sessionId: string) => {
      await api.post(endpoints.sessionStop(sessionId))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
}

export function useResetSession() {
  return useMutation({
    mutationFn: async ({ sessionId, type }: { sessionId: string; type: 'soft' | 'hard' }) => {
      await api.post(endpoints.sessionReset(sessionId, type))
    },
  })
}

export function useCleanupSessions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ApiResponse<number>>(endpoints.sessionCleanup)
      return data.data ?? 0
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })
}
