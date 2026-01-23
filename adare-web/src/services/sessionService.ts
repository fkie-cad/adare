/**
 * Session service - wraps /api/sessions/* endpoints
 */

import { api } from './api'
import type { ApiResponse } from '@/types/api'
import type {
  DevSessionInfo,
  DevSessionListItem,
  StartSessionRequest,
  SessionState,
} from '@/types/session'

export const sessionService = {
  /**
   * Start a new dev session
   */
  async startSession(request: StartSessionRequest): Promise<ApiResponse<DevSessionInfo>> {
    return api.post<DevSessionInfo>('/sessions/start', request)
  },

  /**
   * Stop an active session
   */
  async stopSession(sessionId: string): Promise<ApiResponse<boolean>> {
    return api.post<boolean>(`/sessions/${sessionId}/stop`)
  },

  /**
   * List all active sessions
   */
  async listSessions(): Promise<ApiResponse<DevSessionListItem[]>> {
    return api.get<DevSessionListItem[]>('/sessions')
  },

  /**
   * Get detailed session state
   */
  async getSessionState(sessionId: string): Promise<ApiResponse<SessionState>> {
    return api.get<SessionState>(`/sessions/${sessionId}/state`)
  },

  /**
   * Cleanup stale sessions
   */
  async cleanupSessions(): Promise<ApiResponse<number>> {
    return api.post<number>('/sessions/cleanup')
  },

  /**
   * Reset session (soft or hard)
   */
  async resetSession(sessionId: string, type: 'soft' | 'hard'): Promise<ApiResponse<boolean>> {
    return api.post<boolean>(`/sessions/${sessionId}/reset?type=${type}`)
  },

  /**
   * Check backend health
   */
  async healthCheck(): Promise<ApiResponse<{ status: string; timestamp: string }>> {
    return api.get('/health')
  },
}
