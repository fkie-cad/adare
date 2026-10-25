import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import { unwrap, type ApiResponse } from '@/types/api'

/**
 * Host resources (`/api/system/*`): live load, storage, usage history, run
 * capacity and measured per-run usage. Sizes are bytes, CPU is percent.
 */

export interface DiskInfo {
  path: string
  total_bytes: number
  used_bytes: number
  free_bytes: number
  percent: number
}

export interface RunningVm {
  pid: number
  name: string
  rss_bytes: number
  cpu_percent: number // in cores x 100, like `top`
  started_at: string
  memory_mb: number | null
  cpus: number | null
  // Present when the VM is a registered instance
  instance_id?: string
  status?: string
  vm_name?: string | null
  experiment_run_id?: string | null
}

export interface SystemResources {
  cpu: { count: number; percent: number; load_average: number[] | null }
  memory: {
    total_bytes: number
    available_bytes: number
    used_bytes: number
    swap_total_bytes: number
    swap_used_bytes: number
  }
  disks: DiskInfo[]
  vms: RunningVm[]
  vm_totals: { count: number; rss_bytes: number; cpu_percent: number }
}

export interface StorageCategory {
  key: string
  label: string
  path: string
  bytes: number
  files: number
}

export interface DiskOwner {
  name: string
  bytes: number
  files: number
  state: 'running' | 'registered' | 'orphaned'
  instance_status: string | null
}

export interface ProjectStorage {
  name: string
  path: string
  bytes: number
  files: number
}

export interface StorageReport {
  computed_at: string
  categories: StorageCategory[]
  disk_owners: DiskOwner[]
  projects: ProjectStorage[]
  reclaimable_bytes: number
}

export interface HistoryPoint {
  taken_at: string
  cpu_percent: number
  memory_used_bytes: number
  memory_total_bytes: number
  disk_used_bytes: number
  disk_total_bytes: number
  vm_count: number
  vm_rss_bytes: number
}

export interface RunNeed {
  memory_bytes: number
  cpu_cores: number
  disk_bytes: number
  source: 'measured' | 'configured'
  measured_runs: number
}

export interface EnvironmentCapacity {
  environment: string
  platform: string | null
  need: RunNeed
  fits: number
  fits_by_memory: number
  fits_by_cpu: number
  fits_by_disk: number
  limited_by: 'memory' | 'cpu' | 'disk'
}

export interface Capacity {
  headroom: { memory_bytes: number; cpu_cores: number; disk_bytes: number }
  reserve: { memory_fraction: number; min_memory_bytes: number; disk_fraction: number; min_disk_bytes: number }
  environments: EnvironmentCapacity[]
}

export interface RunUsage {
  id: string
  experiment_run_id: string
  machine: string | null
  environment_name: string | null
  experiment_name: string | null
  project_path: string | null
  started_at: string | null
  ended_at: string | null
  duration_seconds: number | null
  vm_cpus: number | null
  vm_memory_mb: number | null
  peak_rss_bytes: number
  avg_cpu_percent: number
  peak_cpu_percent: number
  disk_bytes: number | null
}

export function useSystemResources(refetchInterval = 3000) {
  return useQuery({
    queryKey: ['system', 'resources'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<SystemResources>>(endpoints.systemResources)
      return unwrap(data, 'Failed to read host resources')
    },
    refetchInterval,
  })
}

export function useSystemCapacity() {
  return useQuery({
    queryKey: ['system', 'capacity'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<Capacity>>(endpoints.systemCapacity)
      return unwrap(data, 'Failed to estimate capacity')
    },
    refetchInterval: 15000,
  })
}

export function useSystemHistory(hours: number) {
  return useQuery({
    queryKey: ['system', 'history', hours],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<HistoryPoint[]>>(endpoints.systemHistory, { params: { hours } })
      return unwrap(data, 'Failed to load usage history')
    },
    refetchInterval: 60000,
  })
}

// Walking the disk takes seconds on a full host; the server caches the report.
const STORAGE_TIMEOUT = 120000

export function useSystemStorage() {
  return useQuery({
    queryKey: ['system', 'storage'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<StorageReport>>(endpoints.systemStorage, {
        timeout: STORAGE_TIMEOUT,
      })
      return unwrap(data, 'Failed to measure storage')
    },
    staleTime: 5 * 60000,
  })
}

export function useRefreshSystemStorage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.get<ApiResponse<StorageReport>>(endpoints.systemStorage, {
        params: { refresh: true },
        timeout: STORAGE_TIMEOUT,
      })
      return unwrap(data, 'Failed to measure storage')
    },
    onSuccess: (report) => qc.setQueryData(['system', 'storage'], report),
  })
}

export function useRunUsage(limit = 50) {
  return useQuery({
    queryKey: ['system', 'run-usage', limit],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<RunUsage[]>>(endpoints.systemRunUsage, { params: { limit } })
      return unwrap(data, 'Failed to load run usage')
    },
    refetchInterval: 60000,
  })
}
