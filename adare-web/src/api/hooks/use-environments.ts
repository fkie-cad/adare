import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

export interface RecipeInfo {
  profile: string
  iso: string
  iso_sha256: string
  template?: string
  setup_level: number
  disk_size?: string
  ram_mb?: number
  cpus?: number
  arch?: string
}

export interface Environment {
  name: string
  project_path?: string
  vm_path?: string
  vm_type?: string
  vm_sha256?: string
  recipe?: RecipeInfo | null
  [key: string]: unknown
}

export interface CreateEnvironmentRequest {
  project_path: string
  name: string
  vm_path?: string
  os_profile?: string
  iso_path?: string
  disk_size?: string
  ram_mb?: number
  cpus?: number
  arch?: string
  setup_level?: number
}

export interface OsProfile {
  name: string
  display_name: string
  platform: string
  distribution: string
  version: string
  architecture: string
  default_disk_size: string
  default_ram_mb: number
  default_cpus: number
}

export interface VerifyEnvironmentRequest {
  name: string
  project_path: string
}

export interface VerifyEnvironmentResponse {
  run_ulid: string
  experiment_name: string
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

export function useOsProfiles() {
  return useQuery({
    queryKey: ['os-profiles'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<OsProfile[]>>(endpoints.osProfiles)
      return data.data ?? []
    },
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

export function useVerifyEnvironment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: VerifyEnvironmentRequest) => {
      const { data } = await api.post<ApiResponse<VerifyEnvironmentResponse>>(
        endpoints.verifyEnvironment(request.name),
        { project_path: request.project_path },
      )
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
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
