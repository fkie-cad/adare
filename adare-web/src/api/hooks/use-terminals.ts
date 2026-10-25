import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import { unwrap, type ApiResponse } from '@/types/api'

/** A PTY session on the host running a shell or Claude Code (see adare/webapi/terminal.py). */
export interface TerminalSession {
  id: string
  title: string
  kind: 'claude' | 'shell'
  cwd: string
  created_at: number
  running: boolean
  exit_code: number | null
}

export interface CreateTerminalRequest {
  kind: 'claude' | 'shell'
  cwd?: string
  prompt?: string
  title?: string
  cols?: number
  rows?: number
}

export function useTerminals(enabled = true) {
  return useQuery({
    queryKey: ['terminals'],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<TerminalSession[]>>(endpoints.terminals)
      return unwrap(data, 'Failed to list terminals')
    },
    enabled,
    refetchInterval: enabled ? 5000 : false,
  })
}

export function useCreateTerminal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (request: CreateTerminalRequest) => {
      const { data } = await api.post<ApiResponse<TerminalSession>>(endpoints.terminals, request)
      return unwrap(data, 'Failed to start terminal')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['terminals'] }),
  })
}

export function useCloseTerminal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(endpoints.terminal(id))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['terminals'] }),
  })
}

/** WebSocket URL for attaching to a terminal (same origin, so the Vite dev proxy forwards it too). */
export function terminalSocketUrl(id: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/terminals/${id}`
}
