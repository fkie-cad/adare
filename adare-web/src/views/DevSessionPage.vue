<template>
  <div class="dev-session-page">
    <div class="page-header">
      <div class="header-left">
        <h1>Dev Session: {{ id }}</h1>
        <span v-if="sessionStore.isConnected" class="connection-status connected">
          <i class="pi pi-circle-fill"></i> Connected
        </span>
        <span v-else class="connection-status disconnected">
          <i class="pi pi-circle-fill"></i> Disconnected
        </span>
      </div>
      <div class="header-actions">
        <Button
          label="Soft Reset"
          icon="pi pi-refresh"
          severity="warning"
          @click="handleReset('soft')"
          text
        />
        <Button
          label="Hard Reset"
          icon="pi pi-replay"
          severity="danger"
          @click="handleReset('hard')"
          text
        />
        <Button
          label="Stop Session"
          icon="pi pi-stop"
          severity="danger"
          @click="handleStop"
        />
      </div>
    </div>

    <div v-if="sessionStore.loading" class="loading-container">
      <ProgressSpinner />
      <p>Loading session...</p>
    </div>

    <div v-else class="session-layout">
      <!-- Left Panel - Action Palette (Placeholder for Phase 3) -->
      <div class="left-panel">
        <h2>Action Palette</h2>
        <p class="placeholder">Action palette will be implemented in Phase 3</p>
        <ul class="action-list">
          <li>Click</li>
          <li>Keyboard</li>
          <li>Scroll</li>
          <li>Wait</li>
          <li>Loop</li>
          <li>Screenshot</li>
          <li>Command</li>
        </ul>
      </div>

      <!-- Center Panel - Quick Execute & Playbook Builder -->
      <div class="center-panel">
        <div class="quick-execute">
          <h2>Quick Execute</h2>
          <p class="hint">Enter YAML action and execute it directly</p>
          <Textarea
            v-model="quickExecuteYaml"
            rows="8"
            placeholder="Click:&#10;  target:&#10;    text: Start Menu&#10;  strategy: best_confidence"
            class="yaml-editor"
          />
          <Button
            label="Execute Action"
            icon="pi pi-play"
            @click="handleExecute"
            :loading="executing"
            :disabled="!quickExecuteYaml.trim()"
          />
        </div>

        <div class="playbook-builder">
          <h2>Playbook Builder</h2>
          <p class="placeholder">Drag-drop canvas will be implemented in Phase 4</p>
        </div>
      </div>

      <!-- Right Panel - Checkpoints, Variables, Execution Log -->
      <div class="right-panel">
        <div class="checkpoints-section">
          <CheckpointPanel :session-id="id" />
        </div>

        <div class="variables-section">
          <VariablesPanel :variables="sessionVariables" />
        </div>

        <div class="execution-section">
          <ExecutionLog :session-id="id" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/sessionStore'
import { useCheckpointStore } from '@/stores/checkpointStore'
import { useExecutionStore } from '@/stores/executionStore'
import { actionService } from '@/services/actionService'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import ProgressSpinner from 'primevue/progressspinner'
import CheckpointPanel from '@/components/checkpoint/CheckpointPanel.vue'
import VariablesPanel from '@/components/session/VariablesPanel.vue'
import ExecutionLog from '@/components/execution/ExecutionLog.vue'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const sessionStore = useSessionStore()
const checkpointStore = useCheckpointStore()
const executionStore = useExecutionStore()
const toast = useToast()

const quickExecuteYaml = ref('')
const executing = ref(false)

// Computed properties
const sessionVariables = computed(() => {
  return sessionStore.sessionState?.variables || {}
})

onMounted(async () => {
  console.log('CLAUDE: DevSessionPage mounted for session:', props.id)

  // Load session state
  await sessionStore.selectSession(props.id)

  // Subscribe stores to WebSocket events
  checkpointStore.subscribeToWebSocket(props.id)
  executionStore.subscribeToWebSocket(props.id)

  // Load initial checkpoint data
  await checkpointStore.fetchCheckpoints(props.id)
})

onUnmounted(() => {
  console.log('CLAUDE: DevSessionPage unmounted')
})

async function handleStop() {
  try {
    await sessionStore.stopSession(props.id)
    toast.add({
      severity: 'success',
      summary: 'Session Stopped',
      detail: 'Session stopped successfully',
      life: 3000
    })
    router.push('/sessions')
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Stop Failed',
      detail: error.message || 'Failed to stop session',
      life: 5000
    })
  }
}

async function handleReset(type: 'soft' | 'hard') {
  try {
    await sessionStore.resetSession(props.id, type)
    toast.add({
      severity: 'success',
      summary: `${type === 'soft' ? 'Soft' : 'Hard'} Reset Complete`,
      detail: 'Session has been reset',
      life: 3000
    })
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Reset Failed',
      detail: error.message || 'Failed to reset session',
      life: 5000
    })
  }
}

async function handleExecute() {
  if (!quickExecuteYaml.value.trim()) {
    toast.add({
      severity: 'warn',
      summary: 'Validation Error',
      detail: 'YAML action is required',
      life: 3000
    })
    return
  }

  executing.value = true
  try {
    const response = await actionService.executeAction(props.id, {
      action_yaml: quickExecuteYaml.value
    })

    if (response.success && response.data) {
      toast.add({
        severity: response.data.success ? 'success' : 'error',
        summary: response.data.success ? 'Action Executed' : 'Action Failed',
        detail: response.data.message,
        life: 3000
      })

      // Clear YAML input on success
      if (response.data.success) {
        quickExecuteYaml.value = ''
      }
    } else {
      toast.add({
        severity: 'error',
        summary: 'Execution Failed',
        detail: response.error || 'Failed to execute action',
        life: 5000
      })
    }
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Execution Error',
      detail: error.message || 'Failed to execute action',
      life: 5000
    })
  } finally {
    executing.value = false
  }
}
</script>

<style scoped>
.dev-session-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.page-header h1 {
  margin: 0;
  font-size: 1.25rem;
}

.connection-status {
  font-size: 0.875rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.connection-status i {
  font-size: 0.5rem;
}

.connection-status.connected {
  color: #059669;
  background: #d1fae5;
}

.connection-status.disconnected {
  color: #dc2626;
  background: #fee2e2;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.loading-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
}

.session-layout {
  display: grid;
  grid-template-columns: 250px 1fr 400px;
  gap: 1rem;
  padding: 1rem;
  height: calc(100% - 80px);
  overflow: hidden;
}

.left-panel,
.center-panel,
.right-panel {
  background: white;
  border-radius: 0.5rem;
  padding: 1.5rem;
  overflow-y: auto;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.left-panel h2,
.center-panel h2,
.right-panel h2 {
  font-size: 1rem;
  margin: 0 0 1rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e2e8f0;
}

.placeholder {
  color: #94a3b8;
  font-style: italic;
  margin: 1rem 0;
  padding: 1rem;
  background: #f1f5f9;
  border-radius: 0.25rem;
  font-size: 0.875rem;
}

.hint {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.75rem;
}

.quick-execute {
  margin-bottom: 2rem;
}

.yaml-editor {
  width: 100%;
  font-family: 'Courier New', monospace;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.quick-execute button {
  width: 100%;
}

.playbook-builder {
  padding-top: 2rem;
  border-top: 1px solid #e5e7eb;
}

.action-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.action-list li {
  padding: 0.5rem;
  margin-bottom: 0.25rem;
  background: #f8fafc;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 0.875rem;
}

.action-list li:hover {
  background: #e2e8f0;
}

.right-panel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.checkpoints-section {
  flex: 0 0 auto;
  max-height: 40%;
  overflow-y: auto;
}

.variables-section {
  flex: 0 0 auto;
  max-height: 30%;
  overflow-y: auto;
}

.execution-section {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>
