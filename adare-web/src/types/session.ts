/**
 * TypeScript types for ADARE dev sessions
 * Mirrors backend DTOs from adare/adare/webapi/
 */

export interface DevSessionInfo {
  session_id: string
  project: string
  experiment: string
  environment: string
  status: 'running' | 'stopped' | 'error'
  created_at: string
  variables: Record<string, any>
  snapshots: CheckpointInfo[]
  action_count: number
  last_action_time?: string
  vm_status: VMStatus
}

export interface DevSessionListItem {
  session_id: string
  project: string
  experiment: string
  environment: string
  status: 'running' | 'stopped' | 'error'
  created_at: string
  action_count: number
  uptime_seconds: number
}

export interface CheckpointInfo {
  name: string
  description?: string
  created_at: string
  memory_size_mb: number
  disk_size_mb: number
  variables_snapshot: Record<string, any>
}

export interface VMStatus {
  hypervisor_type: 'qemu' | 'virtualbox' | 'unknown'
  running: boolean
  websocket_connected: boolean
  last_heartbeat?: string
}

export interface SessionState {
  variables: Record<string, any>
  checkpoints: CheckpointInfo[]
  execution_stats: ExecutionStats
}

export interface ExecutionStats {
  total_actions: number
  successful_actions: number
  failed_actions: number
  average_execution_time_ms: number
}

export interface StartSessionRequest {
  project_path: string
  experiment_name: string
  environment_name: string
  gui_mode?: string
  vm_memory?: number
  vm_cpus?: number
  debug_screenshots?: boolean
}

export interface ResetSessionRequest {
  type: 'soft' | 'hard'
}
