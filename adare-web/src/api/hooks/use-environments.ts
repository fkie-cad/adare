import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

export interface Environment {
  name: string
  project_path?: string
  vm_path?: string
  [key: string]: unknown
}

export interface CreateEnvironmentRequest {
  project_path: string
  name: string
  vm_path?: string
}

export function useEnvironments() {
  return useQuery({
    queryKey: ['environments'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Environment[]>>(endpoints.environments)
      return data.data ?? []
    },
  })
}

export function useEnvironment(name: string) {
  return useQuery({
    queryKey: ['environment', name],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Environment>>(endpoints.environment(name))
      return data.data!
    },
    enabled: !!name,
  })
}

export function useCreateEnvironment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateEnvironmentRequest) => {
      const { data } = await api.post<ApiResponse<Environment>>(endpoints.environments, request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['environments'] }),
  })
}

export function useDeleteEnvironment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, force = false }: { name: string; force?: boolean }) => {
      await api.delete(endpoints.environmentDelete(name, force))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['environments'] }),
  })
}
