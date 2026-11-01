/**
 * TypeScript types for ADARE dev sessions
 * Mirrors backend DTOs from adare/adare/webapi/
 */

/** Mirrors `DevModeSnapshot` (backend/devmode/session/core.py) as serialised by the API. */
export interface SessionSnapshot {
  snapshot_name: string
  created_at: string
  variable_state: Record<string, any>
  description?: string
  memory_file_path?: string
  disk_file_path?: string
  checkpoint_id?: string
}

/** Mirrors `DevSessionInfo` (core/dto/devmode.py): POST /sessions/start and GET /sessions/{id}/state. */
export interface DevSessionInfo {
  session_id: string
  project_path: string
  environment_name: string
  vm_running: boolean
  actions_executed: number
  created_at: string
  current_variables: Record<string, any>
  available_snapshots: SessionSnapshot[]
  experiment_name?: string | null
  name?: string | null
  next_steps?: string[]
  tip?: string | null
}

/** Mirrors `DevSessionListItem` (core/dto/devmode.py): GET /sessions. */
export interface DevSessionListItem {
  session_id: string
  experiment_name: string
  environment_name: string
  vm_running: boolean
  actions_executed: number
  created_at: string
  project_path: string
  status: 'running' | 'stopped' | 'crashed'
  name?: string | null
  vm_name?: string | null
}

/** Mirrors `DevCheckpointInfo` (core/dto/devmode.py): GET /sessions/{id}/checkpoints. */
export interface CheckpointInfo {
  name: string
  description: string
  created_at: string
  variable_count: number
  checkpoint_id: string
  memory_file_path: string
  disk_file_path: string
  file_size_mb: number
}

/** GET /sessions/{id}/state returns the session info itself. */
export type SessionState = DevSessionInfo

/** Mirrors `DevCleanupResult` (core/dto/devmode.py): POST /sessions/cleanup. */
export interface CleanupResult {
  sessions_reconciled: number
  reconciled_session_ids: string[]
  sessions_left_running: number
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
