<template>
  <div class="dev-session-page">
    <div class="page-header">
      <h1>Dev Session: {{ id }}</h1>
      <div class="header-actions">
        <Button label="Stop Session" icon="pi pi-stop" severity="danger" @click="handleStop" />
        <Button label="Reset" icon="pi pi-refresh" severity="warning" @click="handleReset" />
      </div>
    </div>

    <div class="session-layout">
      <div class="left-panel">
        <h2>Action Palette</h2>
        <p class="placeholder">Action palette will be implemented in Phase 3</p>
        <ul>
          <li>Click</li>
          <li>Keyboard</li>
          <li>Scroll</li>
          <li>Wait</li>
          <li>Loop</li>
          <li>Screenshot</li>
          <li>Command</li>
        </ul>
      </div>

      <div class="center-panel">
        <div class="quick-execute">
          <h2>Quick Execute</h2>
          <p class="placeholder">Monaco YAML editor will be implemented here</p>
          <Textarea
            v-model="quickYaml"
            rows="5"
            placeholder="Click:&#10;  target:&#10;    text: Start Menu&#10;  strategy: best_confidence"
            style="width: 100%; font-family: monospace"
          />
          <Button label="Execute Action" icon="pi pi-play" @click="handleExecute" />
        </div>

        <div class="playbook-builder">
          <h2>Playbook Builder</h2>
          <p class="placeholder">Drag-drop canvas will be implemented in Phase 4</p>
        </div>
      </div>

      <div class="right-panel">
        <div class="checkpoints-panel">
          <h2>Checkpoints</h2>
          <Button label="Create Checkpoint" icon="pi pi-save" size="small" @click="handleCreateCheckpoint" />
          <p class="placeholder">Checkpoint list will be shown here</p>
        </div>

        <div class="variables-panel">
          <h2>Variables</h2>
          <p class="placeholder">Session variables will be shown here</p>
        </div>

        <div class="execution-log">
          <h2>Execution Log</h2>
          <p class="placeholder">Real-time action execution log will be shown here</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/sessionStore'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const sessionStore = useSessionStore()
const toast = useToast()

const quickYaml = ref('')

onMounted(() => {
  console.log('CLAUDE: DevSessionPage mounted for session:', props.id)
  sessionStore.selectSession(props.id)
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
      life: 3000,
    })
    router.push('/sessions')
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Stop Failed',
      detail: error instanceof Error ? error.message : 'Unknown error',
      life: 5000,
    })
  }
}

function handleReset() {
  toast.add({
    severity: 'info',
    summary: 'Not Implemented',
    detail: 'Reset functionality will be implemented in Phase 3',
    life: 3000,
  })
}

function handleExecute() {
  toast.add({
    severity: 'info',
    summary: 'Not Implemented',
    detail: 'Action execution will be implemented in Phase 3',
    life: 3000,
  })
}

function handleCreateCheckpoint() {
  toast.add({
    severity: 'info',
    summary: 'Not Implemented',
    detail: 'Checkpoint creation will be implemented in Phase 3',
    life: 3000,
  })
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

.page-header h1 {
  margin: 0;
  font-size: 1.25rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.session-layout {
  display: grid;
  grid-template-columns: 250px 1fr 350px;
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
  padding: 1rem;
  overflow-y: auto;
}

.left-panel h2,
.center-panel h2,
.right-panel h2 {
  font-size: 1rem;
  margin-bottom: 1rem;
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
}

.quick-execute {
  margin-bottom: 2rem;
}

.quick-execute button {
  margin-top: 1rem;
}

.checkpoints-panel,
.variables-panel,
.execution-log {
  margin-bottom: 1.5rem;
}

.checkpoints-panel button {
  margin-bottom: 1rem;
}

ul {
  list-style: none;
  padding: 0;
}

ul li {
  padding: 0.5rem;
  margin-bottom: 0.25rem;
  background: #f8fafc;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: background 0.2s;
}

ul li:hover {
  background: #e2e8f0;
}
</style>
