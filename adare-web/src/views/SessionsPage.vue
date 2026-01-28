<template>
  <div class="sessions-page">
    <div class="page-header">
      <h1>Dev Sessions</h1>
      <div class="header-actions">
        <Button label="Start New Session" icon="pi pi-plus" @click="showStartDialog = true" />
        <Button
          label="Cleanup Stale"
          icon="pi pi-trash"
          severity="secondary"
          @click="handleCleanup"
        />
        <Button label="Refresh" icon="pi pi-refresh" severity="secondary" @click="loadSessions" />
      </div>
    </div>

    <div class="sessions-container">
      <div v-if="sessionStore.loading" class="loading">
        <ProgressSpinner />
        <p>Loading sessions...</p>
      </div>

      <div v-else-if="sessionStore.error" class="error">
        <p>Error: {{ sessionStore.error }}</p>
      </div>

      <div v-else-if="!sessionStore.hasActiveSessions" class="empty-state">
        <i class="pi pi-inbox" style="font-size: 3rem; color: #94a3b8"></i>
        <h2>No active sessions</h2>
        <p>Start a new dev session to begin building playbooks</p>
        <Button label="Start Session" icon="pi pi-plus" @click="showStartDialog = true" />
      </div>

      <div v-else class="sessions-grid">
        <Card v-for="session in sessionStore.sessions" :key="session.session_id" class="session-card">
          <template #header>
            <div class="card-header">
              <span :class="['status-badge', session.status]">{{ session.status }}</span>
            </div>
          </template>
          <template #title>{{ session.project }} / {{ session.experiment }}</template>
          <template #subtitle>{{ session.environment }}</template>
          <template #content>
            <div class="session-info">
              <p><strong>Session ID:</strong> {{ session.session_id.substring(0, 8) }}...</p>
              <p><strong>Actions:</strong> {{ session.action_count }}</p>
              <p><strong>Uptime:</strong> {{ formatUptime(session.uptime_seconds) }}</p>
              <p><strong>Created:</strong> {{ formatDate(session.created_at) }}</p>
            </div>
          </template>
          <template #footer>
            <div class="card-actions">
              <Button
                label="Open"
                icon="pi pi-external-link"
                size="small"
                @click="openSession(session.session_id)"
              />
              <Button
                label="Stop"
                icon="pi pi-stop"
                severity="danger"
                size="small"
                @click="stopSession(session.session_id)"
              />
            </div>
          </template>
        </Card>
      </div>
    </div>

    <Dialog v-model:visible="showStartDialog" header="Start New Dev Session" :modal="true">
      <div class="form-group">
        <label for="project">Project Path</label>
        <InputText id="project" v-model="startForm.project_path" placeholder="/path/to/project" />
      </div>
      <div class="form-group">
        <label for="experiment">Experiment Name</label>
        <InputText id="experiment" v-model="startForm.experiment_name" placeholder="my-experiment" />
      </div>
      <div class="form-group">
        <label for="environment">Environment Name</label>
        <InputText id="environment" v-model="startForm.environment_name" placeholder="win10-env" />
      </div>
      <template #footer>
        <Button label="Cancel" severity="secondary" @click="showStartDialog = false" />
        <Button label="Start Session" @click="handleStartSession" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/sessionStore'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import ProgressSpinner from 'primevue/progressspinner'

const router = useRouter()
const sessionStore = useSessionStore()
const toast = useToast()

const showStartDialog = ref(false)
const startForm = ref({
  project_path: '',
  experiment_name: '',
  environment_name: '',
})

onMounted(() => {
  loadSessions()
})

async function loadSessions() {
  await sessionStore.fetchSessions()
}

async function handleStartSession() {
  if (!startForm.value.project_path || !startForm.value.experiment_name || !startForm.value.environment_name) {
    toast.add({
      severity: 'warn',
      summary: 'Validation Error',
      detail: 'All fields are required',
      life: 3000,
    })
    return
  }

  try {
    const session = await sessionStore.startSession(startForm.value)
    toast.add({
      severity: 'success',
      summary: 'Session Started',
      detail: `Session ${session.session_id.substring(0, 8)}... started successfully`,
      life: 3000,
    })
    showStartDialog.value = false
    router.push(`/session/${session.session_id}`)
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Start Failed',
      detail: error instanceof Error ? error.message : 'Unknown error',
      life: 5000,
    })
  }
}

async function stopSession(sessionId: string) {
  try {
    await sessionStore.stopSession(sessionId)
    toast.add({
      severity: 'success',
      summary: 'Session Stopped',
      detail: `Session ${sessionId.substring(0, 8)}... stopped successfully`,
      life: 3000,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Stop Failed',
      detail: error instanceof Error ? error.message : 'Unknown error',
      life: 5000,
    })
  }
}

async function handleCleanup() {
  try {
    const count = await sessionStore.cleanupSessions()
    toast.add({
      severity: 'success',
      summary: 'Cleanup Complete',
      detail: `Cleaned up ${count} stale session(s)`,
      life: 3000,
    })
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Cleanup Failed',
      detail: error instanceof Error ? error.message : 'Unknown error',
      life: 5000,
    })
  }
}

function openSession(sessionId: string) {
  router.push(`/session/${sessionId}`)
}

function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  return `${hours}h ${minutes}m ${secs}s`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString()
}
</script>

<style scoped>
.sessions-page {
  padding: 2rem;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.page-header h1 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.sessions-container {
  min-height: 400px;
}

.loading,
.error,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
}

.error {
  color: #ef4444;
}

.empty-state h2 {
  margin: 1rem 0 0.5rem;
  color: #64748b;
}

.empty-state p {
  color: #94a3b8;
  margin-bottom: 1.5rem;
}

.sessions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.session-card {
  background: white;
}

.card-header {
  padding: 1rem;
  display: flex;
  justify-content: flex-end;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.running {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.stopped {
  background: #fee2e2;
  color: #991b1b;
}

.status-badge.error {
  background: #fecaca;
  color: #7f1d1d;
}

.session-info p {
  margin: 0.5rem 0;
  color: #64748b;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.form-group input {
  width: 100%;
}
</style>
