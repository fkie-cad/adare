<template>
  <div class="strategy-selector">
    <label for="strategy">Selection Strategy</label>
    <Dropdown
      id="strategy"
      :model-value="modelValue"
      :options="strategies"
      option-label="label"
      option-value="value"
      placeholder="Select strategy"
      @update:model-value="handleChange"
    />
    <small>{{ selectedDescription }}</small>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StrategyType } from '@/types/action'
import Dropdown from 'primevue/dropdown'

interface Props {
  modelValue: StrategyType
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: StrategyType]
}>()

const strategies = [
  {
    value: 'sweep' as StrategyType,
    label: 'Sweep',
    description: 'Scan entire screen systematically',
  },
  {
    value: 'best_confidence' as StrategyType,
    label: 'Best Confidence',
    description: 'Choose match with highest confidence',
  },
  {
    value: 'closest_to' as StrategyType,
    label: 'Closest To',
    description: 'Choose match closest to reference point',
  },
  {
    value: 'leftmost' as StrategyType,
    label: 'Leftmost',
    description: 'Choose leftmost match',
  },
  {
    value: 'rightmost' as StrategyType,
    label: 'Rightmost',
    description: 'Choose rightmost match',
  },
  {
    value: 'topmost' as StrategyType,
    label: 'Topmost',
    description: 'Choose topmost match',
  },
  {
    value: 'bottommost' as StrategyType,
    label: 'Bottommost',
    description: 'Choose bottommost match',
  },
]

const selectedDescription = computed(() => {
  const strategy = strategies.find((s) => s.value === props.modelValue)
  return strategy?.description || ''
})

function handleChange(value: StrategyType) {
  emit('update:modelValue', value)
}
</script>

<style scoped>
.strategy-selector {
  margin-bottom: 1rem;
}

.strategy-selector label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  color: #1e293b;
}

.strategy-selector small {
  display: block;
  margin-top: 0.25rem;
  color: #64748b;
  font-size: 0.85rem;
}
</style>
