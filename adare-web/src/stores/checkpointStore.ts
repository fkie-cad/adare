/**
 * Checkpoint store - manages VM checkpoint state
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { checkpointService } from '@/services/checkpointService'
import type { CheckpointInfo } from '@/types/session'
import type { CreateCheckpointRequest } from '@/types/api'
import { wsManager } from '@/services/websocket'

export const useCheckpointStore = defineStore('checkpoint', () => {
  // State
  const checkpoints = ref<CheckpointInfo[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const hasCheckpoints = computed(() => checkpoints.value.length > 0)
  const checkpointCount = computed(() => checkpoints.value.length)
  const totalDiskSize = computed(() =>
    checkpoints.value.reduce((sum, cp) => sum + cp.disk_size_mb, 0)
  )
  const totalMemorySize = computed(() =>
    checkpoints.value.reduce((sum, cp) => sum + cp.memory_size_mb, 0)
  )

  // Actions
  async function fetchCheckpoints(sessionId: string) {
    loading.value = true
    error.value = null
    try {
      const response = await checkpointService.listCheckpoints(sessionId)
      if (response.success && response.data) {
        checkpoints.value = response.data
      } else {
        throw new Error(response.error || 'Failed to fetch checkpoints')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to fetch checkpoints:', error.value)
    } finally {
      loading.value = false
    }
  }

  async function createCheckpoint(sessionId: string, request: CreateCheckpointRequest) {
    loading.value = true
    error.value = null
    try {
      const response = await checkpointService.createCheckpoint(sessionId, request)
      if (response.success && response.data) {
        // Add to local list
        checkpoints.value.push(response.data)
        return response.data
      } else {
        throw new Error(response.error || 'Failed to create checkpoint')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to create checkpoint:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function restoreCheckpoint(sessionId: string, checkpointName: string) {
    loading.value = true
    error.value = null
    try {
      const response = await checkpointService.restoreCheckpoint(sessionId, checkpointName)
      if (response.success) {
        return true
      } else {
        throw new Error(response.error || 'Failed to restore checkpoint')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to restore checkpoint:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deleteCheckpoint(sessionId: string, checkpointName: string) {
    loading.value = true
    error.value = null
    try {
      const response = await checkpointService.deleteCheckpoint(sessionId, checkpointName)
      if (response.success) {
        // Remove from local list
        const index = checkpoints.value.findIndex((cp) => cp.name === checkpointName)
        if (index !== -1) {
          checkpoints.value.splice(index, 1)
        }
        return true
      } else {
        throw new Error(response.error || 'Failed to delete checkpoint')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to delete checkpoint:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  function subscribeToWebSocket(sessionId: string) {
    const ws = wsManager.getClient(sessionId)

    // Subscribe to checkpoint created events
    ws.on('checkpoint_created', (message) => {
      if (message.data?.checkpoint_info) {
        checkpoints.value.push(message.data.checkpoint_info)
      } else {
        // Refresh list from server
        fetchCheckpoints(sessionId)
      }
    })

    // Subscribe to checkpoint deleted events
    ws.on('checkpoint_deleted', (message) => {
      if (message.data?.checkpoint_name) {
        const index = checkpoints.value.findIndex(
          (cp) => cp.name === message.data.checkpoint_name
        )
        if (index !== -1) {
          checkpoints.value.splice(index, 1)
        }
      }
    })

    // Subscribe to checkpoint restored events (no action needed, just for logging)
    ws.on('checkpoint_restored', (message) => {
      console.log('CLAUDE: Checkpoint restored:', message.data?.checkpoint_name)
    })
  }

  function clearCheckpoints() {
    checkpoints.value = []
  }

  return {
    // State
    checkpoints,
    loading,
    error,

    // Computed
    hasCheckpoints,
    checkpointCount,
    totalDiskSize,
    totalMemorySize,

    // Actions
    fetchCheckpoints,
    createCheckpoint,
    restoreCheckpoint,
    deleteCheckpoint,
    subscribeToWebSocket,
    clearCheckpoints,
  }
})
