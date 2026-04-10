import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse, CreateCheckpointRequest } from '@/types/api'
import type { CheckpointInfo } from '@/types/session'

export function useCheckpoints(sessionId: string) {
  return useQuery({
    queryKey: ['checkpoints', sessionId],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<CheckpointInfo[]>>(endpoints.checkpoints(sessionId))
      return data.data ?? []
    },
    enabled: !!sessionId,
  })
}

export function useCreateCheckpoint(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateCheckpointRequest) => {
      const { data } = await api.post<ApiResponse<CheckpointInfo>>(endpoints.checkpoints(sessionId), request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints', sessionId] }),
  })
}

export function useRestoreCheckpoint(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      await api.post(endpoints.checkpointRestore(sessionId, name))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints', sessionId] }),
  })
}

export function useDeleteCheckpoint(sessionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      await api.delete(endpoints.checkpointDelete(sessionId, name))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints', sessionId] }),
  })
}
