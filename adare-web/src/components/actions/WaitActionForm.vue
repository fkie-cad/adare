<template>
  <div class="wait-action-form">
    <div class="form-group">
      <label for="seconds">Duration (seconds)</label>
      <InputNumber
        id="seconds"
        v-model="seconds"
        :min="0"
        :max="3600"
        :step="0.5"
        placeholder="5"
        @update:model-value="handleUpdate"
      />
      <small>How long to wait (0.5 to 3600 seconds)</small>
    </div>

    <div class="info-box">
      <i class="pi pi-info-circle"></i>
      <p>The Wait action pauses playbook execution for the specified duration.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { WaitAction } from '@/types/action'
import InputNumber from 'primevue/inputnumber'

interface Props {
  action: WaitAction
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: WaitAction]
}>()

const seconds = ref(props.action.seconds || 5)

watch(
  () => props.action,
  (newAction) => {
    seconds.value = newAction.seconds || 5
  }
)

function handleUpdate() {
  const updatedAction: WaitAction = {
    ...props.action,
    type: 'Wait',
    seconds: seconds.value,
  }
  emit('update', updatedAction)
}
</script>

<style scoped>
.wait-action-form {
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

.info-box {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 0.375rem;
  color: #1e40af;
}

.info-box i {
  font-size: 1.25rem;
  margin-top: 0.125rem;
}

.info-box p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
}
</style>
