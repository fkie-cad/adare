<template>
  <div class="execution-log">
    <div class="log-header">
      <h3>Execution Log</h3>
      <div class="stats">
        <span class="stat total">Total: {{ executionStore.totalExecutions }}</span>
        <span class="stat success">✓ {{ executionStore.successfulExecutions }}</span>
        <span class="stat failed">✗ {{ executionStore.failedExecutions }}</span>
      </div>
      <Button
        label="Clear"
        icon="pi pi-trash"
        @click="executionStore.clearLog()"
        size="small"
        text
      />
    </div>

    <div v-if="executionStore.executionLog.length === 0" class="empty-state">
      <p>No actions executed yet</p>
      <p class="hint">Execute actions to see their results here</p>
    </div>

    <ScrollPanel v-else class="log-entries" ref="scrollPanel">
      <div
        v-for="entry in executionStore.executionLog"
        :key="entry.id"
        :class="['log-entry', entry.status]"
      >
        <div class="entry-header">
          <span class="action-type">{{ entry.action_type }}</span>
          <span class="timestamp">{{ formatTime(entry.timestamp) }}</span>
        </div>

        <div v-if="entry.status === 'running'" class="entry-body">
          <ProgressSpinner style="width: 20px; height: 20px" />
          <span class="status-text">Executing...</span>
        </div>

        <div v-else class="entry-body">
          <span :class="['status-icon', entry.status]">
            {{ entry.status === 'success' ? '✓' : '✗' }}
          </span>
          <span class="status-text">
            {{ entry.result?.message || 'Completed' }}
          </span>
          <span v-if="entry.result?.execution_time" class="execution-time">
            ({{ entry.result.execution_time.toFixed(2) }}s)
          </span>
        </div>

        <div v-if="entry.result?.error_message" class="error-message">
          <i class="pi pi-exclamation-triangle"></i>
          {{ entry.result.error_message }}
        </div>

        <div v-if="entry.result?.coordinates" class="coordinates">
          <i class="pi pi-map-marker"></i>
          Coordinates: {{ entry.result.coordinates[0] }}, {{ entry.result.coordinates[1] }}
        </div>
      </div>
    </ScrollPanel>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { useExecutionStore } from '@/stores/executionStore'
import ScrollPanel from 'primevue/scrollpanel'
import ProgressSpinner from 'primevue/progressspinner'
import Button from 'primevue/button'

const props = defineProps<{ sessionId: string }>()
const executionStore = useExecutionStore()
const scrollPanel = ref<InstanceType<typeof ScrollPanel> | null>(null)

onMounted(() => {
  executionStore.subscribeToWebSocket(props.sessionId)
})

// Auto-scroll to bottom on new entries
watch(
  () => executionStore.executionLog.length,
  async () => {
    await nextTick()
    if (scrollPanel.value) {
      const container = scrollPanel.value.$el.querySelector('.p-scrollpanel-content')
      if (container) {
        container.scrollTop = container.scrollHeight
      }
    }
  }
)

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString()
}
</script>

<style scoped>
.execution-log {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #e5e7eb;
}

.log-header h3 {
  margin: 0;
  font-size: 1.2rem;
}

.stats {
  display: flex;
  gap: 1rem;
  font-size: 0.875rem;
}

.stat {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-weight: 500;
}

.stat.total {
  background: #f3f4f6;
  color: #374151;
}

.stat.success {
  background: #d1fae5;
  color: #065f46;
}

.stat.failed {
  background: #fee2e2;
  color: #991b1b;
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

.log-entries {
  flex: 1;
  overflow-y: auto;
}

.log-entry {
  padding: 0.75rem;
  border-bottom: 1px solid #e5e7eb;
  transition: background-color 0.2s;
}

.log-entry:last-child {
  border-bottom: none;
}

.log-entry.running {
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
}

.log-entry.success {
  background: #f0fdf4;
  border-left: 3px solid #10b981;
}

.log-entry.failed {
  background: #fef2f2;
  border-left: 3px solid #ef4444;
}

.entry-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.action-type {
  font-weight: 600;
  color: #374151;
  font-size: 0.875rem;
}

.timestamp {
  font-size: 0.75rem;
  color: #9ca3af;
}

.entry-body {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.status-icon {
  font-weight: bold;
  font-size: 1rem;
}

.status-icon.success {
  color: #10b981;
}

.status-icon.failed {
  color: #ef4444;
}

.status-text {
  color: #374151;
}

.execution-time {
  color: #6b7280;
  font-size: 0.75rem;
  margin-left: auto;
}

.error-message {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  font-size: 0.875rem;
  color: #991b1b;
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.error-message i {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.coordinates {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  font-size: 0.75rem;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.coordinates i {
  color: #3b82f6;
}
</style>
