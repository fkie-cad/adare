<template>
  <div class="keyboard-action-form">
    <div class="mode-selector">
      <label class="field-label">Input Mode</label>
      <div class="radio-group">
        <label>
          <input
            type="radio"
            :checked="mode === 'text'"
            @change="handleModeChange('text')"
          />
          Type Text
        </label>
        <label>
          <input
            type="radio"
            :checked="mode === 'keys'"
            @change="handleModeChange('keys')"
          />
          Press Keys
        </label>
      </div>
    </div>

    <div v-if="mode === 'text'" class="form-group">
      <label for="text">Text to Type</label>
      <InputText
        id="text"
        v-model="text"
        placeholder="Enter text to type..."
        @update:model-value="handleUpdate"
      />
      <small>Text will be typed as-is, supports {{variables}}</small>
    </div>

    <div v-else class="form-group">
      <label for="keys">Keys to Press</label>
      <Textarea
        id="keys"
        v-model="keysText"
        placeholder="Enter keys, one per line (e.g., ctrl+c, enter)"
        :auto-resize="true"
        rows="5"
        @update:model-value="handleUpdate"
      />
      <small>One key combination per line (e.g., "ctrl+c", "enter", "alt+tab")</small>
    </div>

    <div class="form-group">
      <label for="wait">Wait After (seconds)</label>
      <InputNumber
        id="wait"
        v-model="wait"
        :min="0"
        :max="60"
        placeholder="0"
        @update:model-value="handleUpdate"
      />
      <small>Optional delay after typing</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { KeyboardAction } from '@/types/action'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import InputNumber from 'primevue/inputnumber'

interface Props {
  action: KeyboardAction
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: KeyboardAction]
}>()

const mode = ref<'text' | 'keys'>(props.action.text ? 'text' : 'keys')
const text = ref(props.action.text || '')
const keysText = ref(props.action.keys ? props.action.keys.join('\n') : '')
const wait = ref(props.action.wait || 0)

watch(
  () => props.action,
  (newAction) => {
    mode.value = newAction.text ? 'text' : 'keys'
    text.value = newAction.text || ''
    keysText.value = newAction.keys ? newAction.keys.join('\n') : ''
    wait.value = newAction.wait || 0
  }
)

function handleModeChange(newMode: 'text' | 'keys') {
  mode.value = newMode
  handleUpdate()
}

function handleUpdate() {
  const updatedAction: KeyboardAction = {
    ...props.action,
    type: 'Keyboard',
  }

  if (mode.value === 'text') {
    updatedAction.text = text.value
    delete updatedAction.keys
  } else {
    updatedAction.keys = keysText.value
      .split('\n')
      .map((k) => k.trim())
      .filter((k) => k.length > 0)
    delete updatedAction.text
  }

  if (wait.value > 0) {
    updatedAction.wait = wait.value
  }

  emit('update', updatedAction)
}
</script>

<style scoped>
.keyboard-action-form {
  padding: 0.5rem 0;
}

.mode-selector {
  margin-bottom: 1.5rem;
}

.field-label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #1e293b;
}

.radio-group {
  display: flex;
  gap: 1.5rem;
}

.radio-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: normal;
}

.radio-group input[type='radio'] {
  cursor: pointer;
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

.form-group input,
.form-group textarea {
  width: 100%;
}
</style>
