/**
 * Action service - wraps /api/sessions/{id}/actions endpoints
 */

import { api } from './api'
import type { ApiResponse, ExecuteActionRequest, ExecutePlaybookRequest } from '@/types/api'
import type { ActionResult, ActionTypeMetadata } from '@/types/action'

export const actionService = {
  /**
   * Execute a single action from YAML
   */
  async executeAction(
    sessionId: string,
    request: ExecuteActionRequest
  ): Promise<ApiResponse<ActionResult>> {
    return api.post<ActionResult>(`/sessions/${sessionId}/actions/execute`, request)
  },

  /**
   * Execute a full playbook
   */
  async executePlaybook(
    sessionId: string,
    request: ExecutePlaybookRequest
  ): Promise<ApiResponse<ActionResult[]>> {
    return api.post<ActionResult[]>(`/sessions/${sessionId}/playbooks/execute`, request)
  },

  /**
   * Get action type metadata for palette
   */
  async getActionTypes(): Promise<ApiResponse<ActionTypeMetadata[]>> {
    return api.get<ActionTypeMetadata[]>('/actions/types')
  },
}
