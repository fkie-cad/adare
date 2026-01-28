<template>
  <div class="checkpoint-panel">
    <div class="panel-header">
      <h3>Checkpoints ({{ checkpointStore.checkpointCount }})</h3>
      <Button
        label="Create"
        icon="pi pi-plus"
        @click="showCreateDialog = true"
        size="small"
      />
    </div>

    <ProgressSpinner v-if="checkpointStore.loading" />

    <div v-else-if="!checkpointStore.hasCheckpoints" class="empty-state">
      <p>No checkpoints yet</p>
      <p class="hint">Create a checkpoint to save the current VM state</p>
    </div>

    <div v-else class="checkpoint-list">
      <Card
        v-for="cp in checkpointStore.checkpoints"
        :key="cp.name"
        class="checkpoint-card"
      >
        <template #title>{{ cp.name }}</template>
        <template #subtitle>{{ formatDate(cp.created_at) }}</template>
        <template #content>
          <p v-if="cp.description" class="description">{{ cp.description }}</p>
          <div class="checkpoint-info">
            <span class="info-item">
              <i class="pi pi-database"></i>
              Size: {{ cp.file_size_mb.toFixed(2) }} MB
            </span>
            <span class="info-item">
              <i class="pi pi-bookmark"></i>
              Variables: {{ cp.variable_count }}
            </span>
          </div>
        </template>
        <template #footer>
          <div class="card-actions">
            <Button
              label="Restore"
              icon="pi pi-replay"
              @click="handleRestore(cp.name)"
              size="small"
              :loading="restoring === cp.name"
            />
            <Button
              label="Delete"
              icon="pi pi-trash"
              @click="handleDelete(cp.name)"
              severity="danger"
              size="small"
              :loading="deleting === cp.name"
            />
          </div>
        </template>
      </Card>
    </div>

    <!-- Create Dialog -->
    <Dialog
      v-model:visible="showCreateDialog"
      header="Create Checkpoint"
      :modal="true"
      :style="{ width: '450px' }"
    >
      <div class="form-group">
        <label for="checkpoint-name">Name *</label>
        <InputText
          id="checkpoint-name"
          v-model="createForm.name"
          placeholder="e.g., checkpoint-1"
          class="w-full"
        />
      </div>
      <div class="form-group">
        <label for="checkpoint-description">Description (optional)</label>
        <Textarea
          id="checkpoint-description"
          v-model="createForm.description"
          rows="3"
          placeholder="Describe this checkpoint..."
          class="w-full"
        />
      </div>
      <template #footer>
        <Button
          label="Cancel"
          @click="showCreateDialog = false"
          severity="secondary"
          text
        />
        <Button
          label="Create"
          @click="handleCreate"
          :loading="creating"
        />
      </template>
    </Dialog>

    <!-- Delete Confirmation -->
    <Dialog
      v-model:visible="showDeleteDialog"
      header="Confirm Delete"
      :modal="true"
      :style="{ width: '400px' }"
    >
      <p>Delete checkpoint "{{ deleteTarget }}"? This cannot be undone.</p>
      <template #footer>
        <Button
          label="Cancel"
          @click="showDeleteDialog = false"
          severity="secondary"
          text
        />
        <Button
          label="Delete"
          @click="confirmDelete"
          severity="danger"
          :loading="deleting === deleteTarget"
        />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useCheckpointStore } from '@/stores/checkpointStore'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import ProgressSpinner from 'primevue/progressspinner'

const props = defineProps<{ sessionId: string }>()
const checkpointStore = useCheckpointStore()
const toast = useToast()

// Component state
const showCreateDialog = ref(false)
const showDeleteDialog = ref(false)
const deleteTarget = ref('')
const createForm = ref({ name: '', description: '' })
const creating = ref(false)
const restoring = ref<string | null>(null)
const deleting = ref<string | null>(null)

onMounted(async () => {
  await checkpointStore.fetchCheckpoints(props.sessionId)
  checkpointStore.subscribeToWebSocket(props.sessionId)
})

onUnmounted(() => {
  // Cleanup if needed
})

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    toast.add({
      severity: 'warn',
      summary: 'Validation Error',
      detail: 'Name is required',
      life: 3000
    })
    return
  }

  creating.value = true
  try {
    await checkpointStore.createCheckpoint(props.sessionId, createForm.value)
    toast.add({
      severity: 'success',
      summary: 'Checkpoint Created',
      detail: createForm.value.name,
      life: 3000
    })
    showCreateDialog.value = false
    createForm.value = { name: '', description: '' }
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Create Failed',
      detail: error.message || 'Failed to create checkpoint',
      life: 5000
    })
  } finally {
    creating.value = false
  }
}

async function handleRestore(name: string) {
  restoring.value = name
  try {
    await checkpointStore.restoreCheckpoint(props.sessionId, name)
    toast.add({
      severity: 'success',
      summary: 'Checkpoint Restored',
      detail: name,
      life: 3000
    })
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Restore Failed',
      detail: error.message || 'Failed to restore checkpoint',
      life: 5000
    })
  } finally {
    restoring.value = null
  }
}

function handleDelete(name: string) {
  deleteTarget.value = name
  showDeleteDialog.value = true
}

async function confirmDelete() {
  deleting.value = deleteTarget.value
  try {
    await checkpointStore.deleteCheckpoint(props.sessionId, deleteTarget.value)
    toast.add({
      severity: 'success',
      summary: 'Checkpoint Deleted',
      detail: deleteTarget.value,
      life: 3000
    })
    showDeleteDialog.value = false
  } catch (error: any) {
    toast.add({
      severity: 'error',
      summary: 'Delete Failed',
      detail: error.message || 'Failed to delete checkpoint',
      life: 5000
    })
  } finally {
    deleting.value = null
  }
}

function formatDate(date: string): string {
  return new Date(date).toLocaleString()
}
</script>

<style scoped>
.checkpoint-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 1.2rem;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  padding: 2rem;
  text-align: center;
}

.empty-state p {
  margin: 0.25rem 0;
}

.empty-state .hint {
  font-size: 0.875rem;
  color: #9ca3af;
}

.checkpoint-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
  flex: 1;
}

.checkpoint-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.description {
  color: #6b7280;
  font-size: 0.875rem;
  margin-bottom: 0.75rem;
}

.checkpoint-info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #6b7280;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.info-item i {
  font-size: 0.875rem;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #374151;
}

.w-full {
  width: 100%;
}
</style>
