import { create } from 'zustand'
import type { ExecutionLogEntry } from '@/types/api'
import type { ActionResult } from '@/types/action'

interface ExecutionState {
  log: ExecutionLogEntry[]
  addExecution: (actionType: string, description?: string) => string
  updateExecution: (id: string, status: 'success' | 'error', result?: ActionResult) => void
  clearLog: () => void
}

const MAX_LOG_SIZE = 1000

export const useExecutionStore = create<ExecutionState>((set) => ({
  log: [],

  addExecution: (actionType, description) => {
    const id = crypto.randomUUID()
    const entry: ExecutionLogEntry = {
      id,
      timestamp: new Date().toISOString(),
      action_type: actionType,
      description,
      status: 'running',
    }
    set((state) => ({
      log: [entry, ...state.log].slice(0, MAX_LOG_SIZE),
    }))
    return id
  },

  updateExecution: (id, status, result) =>
    set((state) => ({
      log: state.log.map((entry) =>
        entry.id === id
          ? {
              ...entry,
              status,
              result,
              duration_ms: result?.execution_time
                ? result.execution_time * 1000
                : Date.now() - new Date(entry.timestamp).getTime(),
            }
          : entry,
      ),
    })),

  clearLog: () => set({ log: [] }),
}))
