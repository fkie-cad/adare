/**
 * Execution store - manages action execution log and real-time updates
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ExecutionLogEntry } from '@/types/api'
import type { ActionResult } from '@/types/action'
import { wsManager } from '@/services/websocket'

export const useExecutionStore = defineStore('execution', () => {
  // State
  const executionLog = ref<ExecutionLogEntry[]>([])
  const currentExecution = ref<ExecutionLogEntry | null>(null)
  const maxLogSize = ref(1000) // Keep last 1000 entries

  // Computed
  const totalExecutions = computed(() => executionLog.value.length)
  const successfulExecutions = computed(
    () => executionLog.value.filter((e) => e.status === 'success').length
  )
  const failedExecutions = computed(
    () => executionLog.value.filter((e) => e.status === 'error').length
  )
  const runningExecutions = computed(
    () => executionLog.value.filter((e) => e.status === 'running').length
  )
  const averageExecutionTime = computed(() => {
    const completed = executionLog.value.filter((e) => e.duration_ms !== undefined)
    if (completed.length === 0) return 0
    const total = completed.reduce((sum, e) => sum + (e.duration_ms || 0), 0)
    return Math.round(total / completed.length)
  })

  // Actions
  function addExecution(actionType: string, description?: string): string {
    const id = `exec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    const entry: ExecutionLogEntry = {
      id,
      timestamp: new Date().toISOString(),
      action_type: actionType,
      description,
      status: 'running',
    }

    executionLog.value.unshift(entry) // Add to beginning
    currentExecution.value = entry

    // Trim log if it exceeds max size
    if (executionLog.value.length > maxLogSize.value) {
      executionLog.value = executionLog.value.slice(0, maxLogSize.value)
    }

    return id
  }

  function updateExecution(id: string, status: 'success' | 'error', result?: ActionResult) {
    const entry = executionLog.value.find((e) => e.id === id)
    if (entry) {
      entry.status = status
      entry.result = result
      if (result) {
        entry.duration_ms = result.execution_time * 1000 // Convert to ms
      }

      // Clear current execution if this was it
      if (currentExecution.value?.id === id) {
        currentExecution.value = null
      }
    }
  }

  function clearLog() {
    executionLog.value = []
    currentExecution.value = null
  }

  function removeEntry(id: string) {
    const index = executionLog.value.findIndex((e) => e.id === id)
    if (index !== -1) {
      executionLog.value.splice(index, 1)
    }
  }

  function subscribeToWebSocket(sessionId: string) {
    const ws = wsManager.getClient(sessionId)

    // Subscribe to action start events
    ws.on('action_start', (message) => {
      if (message.data) {
        addExecution(message.data.action_type, message.data.description)
      }
    })

    // Subscribe to action complete events
    ws.on('action_complete', (message) => {
      if (message.data && currentExecution.value) {
        updateExecution(currentExecution.value.id, 'success', message.data.result)
      }
    })

    // Subscribe to action error events
    ws.on('action_error', (message) => {
      if (message.data && currentExecution.value) {
        const errorResult: ActionResult = {
          success: false,
          message: message.data.error,
          execution_time: 0,
          error_message: message.data.error,
        }
        updateExecution(currentExecution.value.id, 'error', errorResult)
      }
    })
  }

  return {
    // State
    executionLog,
    currentExecution,
    maxLogSize,

    // Computed
    totalExecutions,
    successfulExecutions,
    failedExecutions,
    runningExecutions,
    averageExecutionTime,

    // Actions
    addExecution,
    updateExecution,
    clearLog,
    removeEntry,
    subscribeToWebSocket,
  }
})
