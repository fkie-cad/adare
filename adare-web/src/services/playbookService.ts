/**
 * Playbook service - wraps /api/playbooks/* endpoints
 */

import { api } from './api'
import type { ApiResponse, SavePlaybookRequest } from '@/types/api'

export const playbookService = {
  /**
   * Save playbook to YAML file
   */
  async savePlaybook(request: SavePlaybookRequest): Promise<ApiResponse<string>> {
    return api.post<string>('/playbooks/save', request)
  },

  /**
   * Load playbook from YAML file
   */
  async loadPlaybook(name: string): Promise<ApiResponse<string>> {
    return api.get<string>(`/playbooks/${name}`)
  },
}
