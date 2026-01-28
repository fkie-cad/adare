<template>
  <div class="command-action-form">
    <div class="form-group">
      <label for="command">Command</label>
      <Textarea
        id="command"
        v-model="command"
        placeholder="Enter shell command..."
        :auto-resize="true"
        rows="5"
        @update:model-value="handleUpdate"
      />
      <small>Shell command to execute (supports {{variables}})</small>
    </div>

    <div class="form-group">
      <label>
        <Checkbox v-model="waitForCompletion" binary @change="handleUpdate" />
        Wait for Completion
      </label>
      <small>Block until command finishes</small>
    </div>

    <div class="form-group">
      <label for="timeout">Timeout (seconds)</label>
      <InputNumber
        id="timeout"
        v-model="timeout"
        :min="0"
        :max="3600"
        placeholder="30"
        @update:model-value="handleUpdate"
      />
      <small>Maximum time to wait for command (0 = no timeout)</small>
    </div>

    <div class="warning-box">
      <i class="pi pi-exclamation-triangle"></i>
      <div>
        <p><strong>Caution:</strong> Commands execute with full system access.</p>
        <p>Ensure commands are safe and do not contain malicious code.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CommandAction } from '@/types/action'
import Textarea from 'primevue/textarea'
import InputNumber from 'primevue/inputnumber'
import Checkbox from 'primevue/checkbox'

interface Props {
  action: CommandAction
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: CommandAction]
}>()

const command = ref(props.action.command || '')
const waitForCompletion = ref(props.action.wait_for_completion !== false)
const timeout = ref(props.action.timeout_seconds || 30)

watch(
  () => props.action,
  (newAction) => {
    command.value = newAction.command || ''
    waitForCompletion.value = newAction.wait_for_completion !== false
    timeout.value = newAction.timeout_seconds || 30
  }
)

function handleUpdate() {
  const updatedAction: CommandAction = {
    ...props.action,
    type: 'Command',
    command: command.value,
    wait_for_completion: waitForCompletion.value,
    timeout_seconds: timeout.value,
  }
  emit('update', updatedAction)
}
</script>

<style scoped>
.command-action-form {
  padding: 0.5rem 0;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #1e293b;
}

.form-group small {
  display: block;
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.85rem;
}

.form-group textarea {
  width: 100%;
  font-family: 'Courier New', monospace;
}

.warning-box {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 0.375rem;
  color: #991b1b;
}

.warning-box i {
  font-size: 1.25rem;
  margin-top: 0.125rem;
  flex-shrink: 0;
}

.warning-box p {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  line-height: 1.5;
}

.warning-box p:last-child {
  margin-bottom: 0;
}
</style>
