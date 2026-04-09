/**
 * TypeScript types for API requests/responses and WebSocket messages
 */

import type { Action, ActionResult } from './action'
import type { SessionState, CheckpointInfo } from './session'

// Generic API response wrapper
export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

// Action execution requests
export interface ExecuteActionRequest {
  action_yaml: string
}

export interface ExecutePlaybookRequest {
  actions: Action[]
  variables?: Record<string, any>
}

// Checkpoint requests
export interface CreateCheckpointRequest {
  name: string
  description?: string
}

// Playbook requests
export interface SavePlaybookRequest {
  name: string
  content: string
}

// WebSocket message types
export type WebSocketMessageType =
  | 'ping'
  | 'pong'
  | 'connected'
  | 'disconnected'
  | 'session_state'
  | 'action_start'
  | 'action_complete'
  | 'action_error'
  | 'vm_status'
  | 'checkpoint_created'
  | 'checkpoint_restored'
  | 'checkpoint_deleted'
  | 'error'

export interface WebSocketMessage {
  type: WebSocketMessageType
  session_id?: string
  data?: any
  timestamp?: string
}

export interface ActionStartMessage extends WebSocketMessage {
  type: 'action_start'
  data: {
    action_type: string
    description?: string
  }
}

export interface ActionCompleteMessage extends WebSocketMessage {
  type: 'action_complete'
  data: {
    action_type: string
    result: ActionResult
  }
}

export interface ActionErrorMessage extends WebSocketMessage {
  type: 'action_error'
  data: {
    action_type: string
    error: string
  }
}

export interface SessionStateMessage extends WebSocketMessage {
  type: 'session_state'
  data: SessionState
}

export interface VMStatusMessage extends WebSocketMessage {
  type: 'vm_status'
  data: {
    running: boolean
    websocket_connected: boolean
  }
}

export interface CheckpointEventMessage extends WebSocketMessage {
  type: 'checkpoint_created' | 'checkpoint_restored' | 'checkpoint_deleted'
  data: {
    checkpoint_name: string
    checkpoint_info?: CheckpointInfo
  }
}

// Execution log entry (for frontend only)
export interface ExecutionLogEntry {
  id: string
  timestamp: string
  action_type: string
  description?: string
  status: 'running' | 'success' | 'error'
  result?: ActionResult
  duration_ms?: number
}
