/**
 * Checkpoint service - wraps /api/sessions/{id}/checkpoints endpoints
 */

import { api } from './api'
import type { ApiResponse, CreateCheckpointRequest } from '@/types/api'
import type { CheckpointInfo } from '@/types/session'

export const checkpointService = {
  /**
   * Create a new checkpoint
   */
  async createCheckpoint(
    sessionId: string,
    request: CreateCheckpointRequest
  ): Promise<ApiResponse<CheckpointInfo>> {
    return api.post<CheckpointInfo>(`/sessions/${sessionId}/checkpoints`, request)
  },

  /**
   * List all checkpoints for a session
   */
  async listCheckpoints(sessionId: string): Promise<ApiResponse<CheckpointInfo[]>> {
    return api.get<CheckpointInfo[]>(`/sessions/${sessionId}/checkpoints`)
  },

  /**
   * Restore a checkpoint
   */
  async restoreCheckpoint(sessionId: string, checkpointName: string): Promise<ApiResponse<boolean>> {
    return api.post<boolean>(`/sessions/${sessionId}/checkpoints/${checkpointName}/restore`)
  },

  /**
   * Delete a checkpoint
   */
  async deleteCheckpoint(sessionId: string, checkpointName: string): Promise<ApiResponse<boolean>> {
    return api.delete<boolean>(`/sessions/${sessionId}/checkpoints/${checkpointName}`)
  },
}
