import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

/** One run row / run detail as the backend sends it (RunListItem / RunDetail). */
export interface Run {
  ulid: string
  /** `Project.experiment` dotnotation; links to /experiments/$name. */
  experiment_name?: string
  experiment_ulid?: string
  environment_name?: string
  environment_ulid?: string
  project_name?: string
  start_time?: string
  end_time?: string
  duration_seconds?: number
  status?: string
  /** Verdict computed from the run's test results (SUCCESS, FAILED, INCONCLUSIVE, WARNING, TEST_MISSING, ...). */
  result_status?: string
  published?: boolean
  fake?: boolean
  [key: string]: unknown
}

export interface RunTestResult {
  name: string
  /** StatusEnum name of the stored result, e.g. SUCCESS / FAILED / WARNING / INCONCLUSIVE. */
  status: string
  passed: boolean
  details: string
}

/** Run detail: the row plus what only the run page shows. */
export interface RunDetail extends Run {
  /** Absent when the run's environment is unknown or has no VM / OsInfo. */
  os_info?: string | null
  vm_box?: string | null
  test_results?: RunTestResult[]
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

/** Run statuses (StatusEnum names) of a run that has not finished yet. */
const ACTIVE_RUN_STATUSES = new Set(['RUNNING', 'PENDING', 'PAUSE'])

export function isActiveRun(run: Run): boolean {
  return ACTIVE_RUN_STATUSES.has((run.status ?? '').toUpperCase())
}

/**
 * Runs, newest first (the backend sorts by start time across projects).
 * Polls so runs started from the CLI show up: fast while one is active, slower otherwise.
 */
export function useRuns(filter?: ListRunsFilter, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['runs', filter ?? {}],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Run[]>>(buildRunsUrl(filter))
      return data.data ?? []
    },
    enabled: options?.enabled ?? true,
    refetchInterval: (query) => (query.state.data?.some(isActiveRun) ? 5_000 : 15_000),
  })
}

export function useRun(ulid: string) {
  return useQuery({
    queryKey: ['run', ulid],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<RunDetail>>(endpoints.run(ulid))
      return data.data!
    },
    enabled: !!ulid,
  })
}

export interface RunArtifact {
  path: string
  kind: 'screenshot' | 'video' | 'report' | 'log' | 'other'
  size: number
}

export function useRunArtifacts(ulid: string) {
  return useQuery({
    queryKey: ['run-artifacts', ulid],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<RunArtifact[]>>(endpoints.runArtifacts(ulid))
      return data.data ?? []
    },
    enabled: !!ulid,
  })
}

export function useRemoveRun() {
  const qc = useQueryClient()
  return useMutation({
    // The backend finds the run's project from the ULID, so no project path is needed.
    mutationFn: async ({ ulid }: { ulid: string }) => {
      await api.delete(endpoints.run(ulid))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  })
}
