<template>
  <div class="click-action-form">
    <TargetInput v-model="target" @update:model-value="handleUpdate" />

    <StrategySelector v-model="strategy" @update:model-value="handleUpdate" />

    <div class="form-group">
      <label for="button">Mouse Button</label>
      <Dropdown
        id="button"
        v-model="button"
        :options="buttonOptions"
        option-label="label"
        option-value="value"
        @update:model-value="handleUpdate"
      />
    </div>

    <div class="form-group">
      <label>
        <Checkbox v-model="doubleClick" binary @change="handleUpdate" />
        Double Click
      </label>
    </div>

    <div class="form-group">
      <label for="offset-x">Offset X (pixels)</label>
      <InputNumber
        id="offset-x"
        v-model="offsetX"
        placeholder="0"
        @update:model-value="handleUpdate"
      />
    </div>

    <div class="form-group">
      <label for="offset-y">Offset Y (pixels)</label>
      <InputNumber
        id="offset-y"
        v-model="offsetY"
        placeholder="0"
        @update:model-value="handleUpdate"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ClickAction, Target, StrategyType, MouseButton } from '@/types/action'
import Dropdown from 'primevue/dropdown'
import Checkbox from 'primevue/checkbox'
import InputNumber from 'primevue/inputnumber'
import TargetInput from '@/components/common/TargetInput.vue'
import StrategySelector from '@/components/common/StrategySelector.vue'

interface Props {
  action: ClickAction
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: ClickAction]
}>()

const target = ref<Target>(props.action.target || { type: 'text', text: '' })
const strategy = ref<StrategyType>(props.action.strategy || 'sweep')
const button = ref<MouseButton>(props.action.button || 'left')
const doubleClick = ref(props.action.double_click || false)
const offsetX = ref(props.action.offset_x || 0)
const offsetY = ref(props.action.offset_y || 0)

const buttonOptions = [
  { label: 'Left', value: 'left' },
  { label: 'Right', value: 'right' },
  { label: 'Middle', value: 'middle' },
]

watch(
  () => props.action,
  (newAction) => {
    target.value = newAction.target || { type: 'text', text: '' }
    strategy.value = newAction.strategy || 'sweep'
    button.value = newAction.button || 'left'
    doubleClick.value = newAction.double_click || false
    offsetX.value = newAction.offset_x || 0
    offsetY.value = newAction.offset_y || 0
  }
)

function handleUpdate() {
  const updatedAction: ClickAction = {
    ...props.action,
    target: target.value,
    strategy: strategy.value,
    button: button.value,
    double_click: doubleClick.value,
    offset_x: offsetX.value,
    offset_y: offsetY.value,
  }
  emit('update', updatedAction)
}
</script>

<style scoped>
.click-action-form {
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

.form-group input,
.form-group select {
  width: 100%;
}
</style>
