<template>
  <div class="screenshot-action-form">
    <div class="form-group">
      <label for="filename">Filename</label>
      <InputText
        id="filename"
        v-model="filename"
        placeholder="screenshot.png"
        @update:model-value="handleUpdate"
      />
      <small>Filename for the screenshot (supports {{variables}})</small>
    </div>

    <div class="form-group">
      <label>
        <Checkbox v-model="useRegion" binary @change="handleRegionToggle" />
        Capture Specific Region
      </label>
    </div>

    <div v-if="useRegion" class="region-config">
      <div class="region-grid">
        <div class="region-field">
          <label for="region-x">X</label>
          <InputNumber
            id="region-x"
            v-model="regionX"
            :min="0"
            placeholder="0"
            @update:model-value="handleUpdate"
          />
        </div>

        <div class="region-field">
          <label for="region-y">Y</label>
          <InputNumber
            id="region-y"
            v-model="regionY"
            :min="0"
            placeholder="0"
            @update:model-value="handleUpdate"
          />
        </div>

        <div class="region-field">
          <label for="region-width">Width</label>
          <InputNumber
            id="region-width"
            v-model="regionWidth"
            :min="1"
            placeholder="800"
            @update:model-value="handleUpdate"
          />
        </div>

        <div class="region-field">
          <label for="region-height">Height</label>
          <InputNumber
            id="region-height"
            v-model="regionHeight"
            :min="1"
            placeholder="600"
            @update:model-value="handleUpdate"
          />
        </div>
      </div>
      <small>Specify rectangular region in pixels (x, y, width, height)</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ScreenshotAction } from '@/types/action'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Checkbox from 'primevue/checkbox'

interface Props {
  action: ScreenshotAction
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: ScreenshotAction]
}>()

const filename = ref(props.action.filename || 'screenshot.png')
const useRegion = ref(!!props.action.region)
const regionX = ref(props.action.region?.x || 0)
const regionY = ref(props.action.region?.y || 0)
const regionWidth = ref(props.action.region?.width || 800)
const regionHeight = ref(props.action.region?.height || 600)

watch(
  () => props.action,
  (newAction) => {
    filename.value = newAction.filename || 'screenshot.png'
    useRegion.value = !!newAction.region
    regionX.value = newAction.region?.x || 0
    regionY.value = newAction.region?.y || 0
    regionWidth.value = newAction.region?.width || 800
    regionHeight.value = newAction.region?.height || 600
  }
)

function handleRegionToggle() {
  handleUpdate()
}

function handleUpdate() {
  const updatedAction: ScreenshotAction = {
    ...props.action,
    type: 'Screenshot',
    filename: filename.value,
  }

  if (useRegion.value) {
    updatedAction.region = {
      x: regionX.value,
      y: regionY.value,
      width: regionWidth.value,
      height: regionHeight.value,
    }
  } else {
    delete updatedAction.region
  }

  emit('update', updatedAction)
}
</script>

<style scoped>
.screenshot-action-form {
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

.region-config {
  margin-top: 1rem;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 0.375rem;
}

.region-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.region-field label {
  display: block;
  margin-bottom: 0.25rem;
  font-weight: 500;
  font-size: 0.85rem;
  color: #475569;
}
</style>
