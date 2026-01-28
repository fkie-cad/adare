<template>
  <div class="generic-action-form">
    <div class="info-box">
      <i class="pi pi-info-circle"></i>
      <div>
        <p><strong>{{ action.type }} Action</strong></p>
        <p>This action type does not have a dedicated configuration form yet.</p>
        <p>You can edit the raw YAML parameters below or use the YAML editor.</p>
      </div>
    </div>

    <div class="form-group">
      <label for="json-params">Parameters (JSON)</label>
      <Textarea
        id="json-params"
        v-model="jsonParams"
        :auto-resize="true"
        rows="10"
        @update:model-value="handleUpdate"
      />
      <small>Edit action parameters as JSON</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Action } from '@/types/action'
import Textarea from 'primevue/textarea'

interface Props {
  action: Action
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: Action]
}>()

const jsonParams = ref(JSON.stringify(props.action, null, 2))

watch(
  () => props.action,
  (newAction) => {
    jsonParams.value = JSON.stringify(newAction, null, 2)
  }
)

function handleUpdate() {
  try {
    const parsed = JSON.parse(jsonParams.value)
    emit('update', parsed)
  } catch (err) {
    console.error('CLAUDE: Invalid JSON in generic action form:', err)
  }
}
</script>

<style scoped>
.generic-action-form {
  padding: 0.5rem 0;
}

.info-box {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 0.375rem;
  color: #1e40af;
  margin-bottom: 1.5rem;
}

.info-box i {
  font-size: 1.25rem;
  margin-top: 0.125rem;
  flex-shrink: 0;
}

.info-box p {
  margin: 0 0 0.5rem 0;
  font-size: 0.9rem;
  line-height: 1.5;
}

.info-box p:last-child {
  margin-bottom: 0;
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
  font-size: 0.85rem;
}
</style>
