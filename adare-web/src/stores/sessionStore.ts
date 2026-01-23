/**
 * Session store - manages dev session state
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sessionService } from '@/services/sessionService'
import type {
  DevSessionInfo,
  DevSessionListItem,
  StartSessionRequest,
  SessionState,
} from '@/types/session'
import { wsManager } from '@/services/websocket'

export const useSessionStore = defineStore('session', () => {
  // State
  const sessions = ref<DevSessionListItem[]>([])
  const currentSession = ref<DevSessionInfo | null>(null)
  const sessionState = ref<SessionState | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const hasActiveSessions = computed(() => sessions.value.length > 0)
  const currentSessionId = computed(() => currentSession.value?.session_id)
  const isConnected = computed(() => {
    if (!currentSessionId.value) return false
    const ws = wsManager.getClient(currentSessionId.value)
    return ws.isConnected()
  })

  // Actions
  async function fetchSessions() {
    loading.value = true
    error.value = null
    try {
      const response = await sessionService.listSessions()
      if (response.success && response.data) {
        sessions.value = response.data
      } else {
        throw new Error(response.error || 'Failed to fetch sessions')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to fetch sessions:', error.value)
    } finally {
      loading.value = false
    }
  }

  async function startSession(request: StartSessionRequest) {
    loading.value = true
    error.value = null
    try {
      const response = await sessionService.startSession(request)
      if (response.success && response.data) {
        currentSession.value = response.data
        await fetchSessions() // Refresh session list

        // Connect WebSocket for real-time updates
        connectWebSocket(response.data.session_id)

        return response.data
      } else {
        throw new Error(response.error || 'Failed to start session')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to start session:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function stopSession(sessionId: string) {
    loading.value = true
    error.value = null
    try {
      const response = await sessionService.stopSession(sessionId)
      if (response.success) {
        // Disconnect WebSocket
        wsManager.removeClient(sessionId)

        // Clear current session if it's the one being stopped
        if (currentSession.value?.session_id === sessionId) {
          currentSession.value = null
          sessionState.value = null
        }

        await fetchSessions() // Refresh session list
      } else {
        throw new Error(response.error || 'Failed to stop session')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to stop session:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function selectSession(sessionId: string) {
    loading.value = true
    error.value = null
    try {
      const response = await sessionService.getSessionState(sessionId)
      if (response.success && response.data) {
        sessionState.value = response.data

        // Connect WebSocket if not already connected
        connectWebSocket(sessionId)
      } else {
        throw new Error(response.error || 'Failed to get session state')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to select session:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function resetSession(sessionId: string, type: 'soft' | 'hard') {
    loading.value = true
    error.value = null
    try {
      const response = await sessionService.resetSession(sessionId, type)
      if (response.success) {
        // Refresh session state after reset
        await selectSession(sessionId)
      } else {
        throw new Error(response.error || 'Failed to reset session')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to reset session:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function cleanupSessions() {
    loading.value = true
    error.value = null
    try {
      const response = await sessionService.cleanupSessions()
      if (response.success) {
        await fetchSessions() // Refresh session list
        return response.data || 0
      } else {
        throw new Error(response.error || 'Failed to cleanup sessions')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to cleanup sessions:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  function connectWebSocket(sessionId: string) {
    const ws = wsManager.getClient(sessionId)

    // Subscribe to session state updates
    ws.on('session_state', (message) => {
      if (message.data) {
        sessionState.value = message.data
      }
    })

    // Subscribe to VM status updates
    ws.on('vm_status', (message) => {
      if (currentSession.value && message.data) {
        currentSession.value.vm_status = {
          ...currentSession.value.vm_status,
          ...message.data,
        }
      }
    })

    // Connect
    ws.connect()
  }

  function disconnectWebSocket(sessionId: string) {
    wsManager.removeClient(sessionId)
  }

  return {
    // State
    sessions,
    currentSession,
    sessionState,
    loading,
    error,

    // Computed
    hasActiveSessions,
    currentSessionId,
    isConnected,

    // Actions
    fetchSessions,
    startSession,
    stopSession,
    selectSession,
    resetSession,
    cleanupSessions,
    connectWebSocket,
    disconnectWebSocket,
  }
})
