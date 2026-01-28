<template>
  <div class="target-input">
    <label class="field-label">Target</label>

    <div class="target-type-selector">
      <div class="radio-group">
        <label>
          <input
            type="radio"
            :checked="modelValue.type === 'image'"
            @change="handleTypeChange('image')"
          />
          Image
        </label>
        <label>
          <input
            type="radio"
            :checked="modelValue.type === 'text'"
            @change="handleTypeChange('text')"
          />
          Text
        </label>
      </div>
    </div>

    <div v-if="modelValue.type === 'image'" class="target-config">
      <label>Image Path</label>
      <InputText
        :model-value="modelValue.image || ''"
        placeholder="path/to/image.png"
        @update:model-value="handleImageChange"
      />
      <small>Path to reference image file</small>
    </div>

    <div v-else class="target-config">
      <label>Search Text</label>
      <InputText
        :model-value="modelValue.text || ''"
        placeholder="Button text or search term"
        @update:model-value="handleTextChange"
      />
      <small>Text to search for on screen</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Target } from '@/types/action'
import InputText from 'primevue/inputtext'

interface Props {
  modelValue: Target
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: Target]
}>()

function handleTypeChange(type: 'image' | 'text') {
  const newTarget: Target = {
    type,
    ...(type === 'image' ? { image: props.modelValue.image || '' } : { text: props.modelValue.text || '' }),
  }
  emit('update:modelValue', newTarget)
}

function handleImageChange(value: string) {
  emit('update:modelValue', {
    type: 'image',
    image: value,
  })
}

function handleTextChange(value: string) {
  emit('update:modelValue', {
    type: 'text',
    text: value,
  })
}
</script>

<style scoped>
.target-input {
  margin-bottom: 1rem;
}

.field-label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #1e293b;
}

.target-type-selector {
  margin-bottom: 1rem;
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

.target-config {
  margin-top: 1rem;
}

.target-config label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  font-size: 0.9rem;
}

.target-config small {
  display: block;
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.85rem;
}
</style>
