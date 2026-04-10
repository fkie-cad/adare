import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

export interface Project {
  name: string
  path: string
  description?: string
  [key: string]: unknown
}

export interface CreateProjectRequest {
  name: string
  path: string
  description?: string
}

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Project[]>>(endpoints.projects)
      return data.data ?? []
    },
  })
}

export function useProject(projectPath: string) {
  return useQuery({
    queryKey: ['project', projectPath],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Project>>(endpoints.project(projectPath))
      return data.data!
    },
    enabled: !!projectPath,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateProjectRequest) => {
      const { data } = await api.post<ApiResponse<Project>>(endpoints.projects, request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, path }: { name: string; path?: string }) => {
      await api.delete(endpoints.projectDelete(name, path))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })
}
