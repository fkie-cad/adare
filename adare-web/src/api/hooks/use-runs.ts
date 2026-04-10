import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

export interface Run {
  ulid: string
  project?: string
  environment?: string
  experiment?: string
  [key: string]: unknown
}

export interface ListRunsFilter {
  project?: string
  environment?: string
  experiment?: string
}

function buildRunsUrl(filter?: ListRunsFilter): string {
  if (!filter) return endpoints.runs
  const params = new URLSearchParams()
  if (filter.project) params.set('project', filter.project)
  if (filter.environment) params.set('environment', filter.environment)
  if (filter.experiment) params.set('experiment', filter.experiment)
  const qs = params.toString()
  return qs ? `${endpoints.runs}?${qs}` : endpoints.runs
}

export function useRuns(filter?: ListRunsFilter) {
  return useQuery({
    queryKey: ['runs', filter ?? {}],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Run[]>>(buildRunsUrl(filter))
      return data.data ?? []
    },
  })
}

export function useRun(ulid: string) {
  return useQuery({
    queryKey: ['run', ulid],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Run>>(endpoints.run(ulid))
      return data.data!
    },
    enabled: !!ulid,
  })
}

export function useRemoveRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ ulid, projectPath }: { ulid: string; projectPath?: string }) => {
      const url = projectPath
        ? `${endpoints.run(ulid)}?project_path=${encodeURIComponent(projectPath)}`
        : endpoints.run(ulid)
      await api.delete(url)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}
