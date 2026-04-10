import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

export interface Experiment {
  name: string
  project_path?: string
  tags?: string[]
  [key: string]: unknown
}

export interface CreateExperimentRequest {
  project_path: string
  name: string
}

export interface CloneExperimentRequest {
  project_path: string
  target_experiment: string
  environments?: string[]
}

export interface RemoveExperimentRequest {
  project_path: string
  force?: boolean
  keep_files?: boolean
}

export interface ValidateExperimentRequest {
  project_path: string
  environment?: string
}

export function useExperiments(tags?: string[]) {
  const tagsParam = tags?.join(',') ?? ''
  return useQuery({
    queryKey: ['experiments', tagsParam],
    queryFn: async () => {
      const url = tagsParam ? endpoints.experimentsByTags(tagsParam) : endpoints.experiments
      const { data } = await api.get<ApiResponse<Experiment[]>>(url)
      return data.data ?? []
    },
  })
}

export function useExperiment(name: string) {
  return useQuery({
    queryKey: ['experiment', name],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Experiment>>(endpoints.experiment(name))
      return data.data!
    },
    enabled: !!name,
  })
}

export function useCreateExperiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateExperimentRequest) => {
      const { data } = await api.post<ApiResponse<Experiment>>(endpoints.experiments, request)
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['experiments'] }),
  })
}

export function useCloneExperiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, request }: { name: string; request: CloneExperimentRequest }) => {
      const { data } = await api.post<ApiResponse<Experiment>>(
        endpoints.experimentClone(name),
        request,
      )
      return data.data!
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['experiments'] }),
  })
}

export function useRemoveExperiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, request }: { name: string; request: RemoveExperimentRequest }) => {
      await api.delete(endpoints.experiment(name), { data: request })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['experiments'] }),
  })
}

export function useValidateExperiment() {
  return useMutation({
    mutationFn: async ({ name, request }: { name: string; request: ValidateExperimentRequest }) => {
      const { data } = await api.post<ApiResponse<unknown>>(
        endpoints.experimentValidate(name),
        request,
      )
      return data.data
    },
  })
}
