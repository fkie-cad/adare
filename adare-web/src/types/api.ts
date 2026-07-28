/**
 * TypeScript types for API requests/responses and WebSocket messages
 */

import type { Action, ActionResult } from './action'
import type { SessionState, CheckpointInfo } from './session'

// Structured failure detail. This is what the backend actually sends: every
// webapi route funnels failures through `result_to_response`
// (adare/adare/webapi/adapters.py), which emits
// `{success: false, error: {code, message, solutions}}` — an object, not a string.
export interface ApiError {
  code: string
  message: string
  solutions?: string[]
}

// Generic API response wrapper.
//
// NOTE ON `error`: it was previously typed `string`, which no route has ever sent.
// Reading it as a string yielded "[object Object]". `string` is retained in the
// union only because nothing guarantees a hand-rolled route somewhere returns the
// object shape — consumers should handle both.
//
// NOTE ON STATUS CODES: a failure arrives as **HTTP 200** with `success: false`,
// not a 4xx. axios therefore resolves, and the response interceptor in
// `api/client.ts` never sees it. A hook that does `return data.data!` will silently
// resolve a rejection as a success — check `data.success === false` first. See
// `useCreateEnvironment` in `api/hooks/use-environments.ts` for the pattern.
export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string | ApiError
  message?: string
}

// Render a webapi failure as one human-readable line.
//
// `error` is an *object* on every `result_to_response` route even though the type
// above allows `string`, so both shapes are accepted. It is read as
// `Partial<ApiError>` rather than `ApiError`: this is an unvalidated wire value, so
// neither field is guaranteed present even though the type declares them required.
export function apiErrorMessage(error: unknown): string | null {
  if (!error) return null
  if (typeof error === 'string') return error
  if (typeof error !== 'object') return null
  const { code, message, solutions } = error as Partial<ApiError>
  const head = message ?? code
  if (!head) return null
  // The server's `solutions` are what make a rejection actionable (e.g. which
  // published URL to use instead of a BYO name), so surface them too.
  const hint = solutions?.filter((s) => s.trim().length > 0).join(' ')
  return hint ? `${head} ${hint}` : head
}

/**
 * Throw if the server rejected the request; otherwise do nothing.
 *
 * Use this in every hook whose route funnels through `result_to_response`. A
 * rejection arrives as **HTTP 200** with `success: false`, so axios resolves and
 * the response interceptor in `api/client.ts` never sees it — a hook that does
 * `return data.data!` resolves a rejection as a success, firing the success toast
 * and hiding the reason. `?? []` is just as bad in a different way: it turns a
 * failed list call into a convincing "nothing here yet".
 *
 * For a route that returns no payload (a DELETE), this is the whole check.
 */
export function assertOk(response: ApiResponse<unknown>, fallbackMessage: string): void {
  if (response.success === false) {
    throw new Error(apiErrorMessage(response.error ?? response.message) ?? fallbackMessage)
  }
}

/** Return a response's payload, throwing on rejection *or* on a missing payload. */
export function unwrap<T>(response: ApiResponse<T>, fallbackMessage: string): T {
  assertOk(response, fallbackMessage)
  if (response.data === undefined || response.data === null) {
    throw new Error(fallbackMessage)
  }
  return response.data
}

/**
 * Like {@link unwrap}, but substitutes `fallbackValue` when the call succeeded and
 * simply carried no payload. Use for list endpoints, where an *absent* list on a
 * successful response legitimately means "none" — a rejection still throws.
 */
export function unwrapOr<T>(
  response: ApiResponse<T>,
  fallbackMessage: string,
  fallbackValue: T,
): T {
  assertOk(response, fallbackMessage)
  return response.data ?? fallbackValue
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

// Playbook requests — mirrors the actual backend contract
// (adare/adare/webapi/main.py: POST /api/playbooks/save, GET /api/playbooks/{filename}),
// which takes/returns structured actions+settings, not a YAML string.
export interface SavePlaybookRequest {
  filename: string
  actions: Action[]
  settings?: Record<string, unknown>
}

export interface PlaybookData {
  actions: Action[]
  settings: Record<string, unknown>
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
  | 'agent_step'
  | 'agent_status'
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

export interface AgentStepMessage extends WebSocketMessage {
  type: 'agent_step'
  data: {
    phase: 'decided' | 'executed' | 'pause' | 'resume'
    index: number
    kind: string
    describe: string
    reasoning: string
    coords: [number, number] | null
    grounded: boolean
    status: string
    screenshot: string | null
  }
}

export interface AgentStatusMessage extends WebSocketMessage {
  type: 'agent_status'
  data: {
    state: 'running' | 'finished' | 'failed'
    summary: string
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
