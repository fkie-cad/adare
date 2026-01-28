<template>
  <div class="variables-panel">
    <div class="panel-header">
      <h3>Variables ({{ variableCount }})</h3>
    </div>

    <div v-if="variableCount === 0" class="empty-state">
      <p>No variables set</p>
      <p class="hint">Variables will appear here after action execution</p>
    </div>

    <DataTable
      v-else
      :value="variableEntries"
      class="variables-table"
      striped-rows
      scrollable
      scroll-height="flex"
    >
      <Column field="key" header="Name" :sortable="true">
        <template #body="slotProps">
          <span class="variable-name">{{ slotProps.data.key }}</span>
        </template>
      </Column>
      <Column field="value" header="Value">
        <template #body="slotProps">
          <span class="variable-value">{{ formatValue(slotProps.data.value) }}</span>
        </template>
      </Column>
      <Column field="type" header="Type" :sortable="true">
        <template #body="slotProps">
          <Tag :value="slotProps.data.type" :severity="getTypeSeverity(slotProps.data.type)" />
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'

const props = defineProps<{
  variables: Record<string, any>
}>()

const variableCount = computed(() => Object.keys(props.variables || {}).length)

const variableEntries = computed(() => {
  return Object.entries(props.variables || {}).map(([key, value]) => ({
    key,
    value,
    type: getTypeString(value)
  }))
})

function getTypeString(value: any): string {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  return typeof value
}

function formatValue(value: any): string {
  if (value === null) return 'null'
  if (value === undefined) return 'undefined'

  if (typeof value === 'object') {
    const jsonStr = JSON.stringify(value, null, 2)
    // Truncate long values
    if (jsonStr.length > 100) {
      return jsonStr.substring(0, 100) + '...'
    }
    return jsonStr
  }

  const strValue = String(value)
  // Truncate long strings
  if (strValue.length > 100) {
    return strValue.substring(0, 100) + '...'
  }
  return strValue
}

function getTypeSeverity(type: string): string {
  switch (type) {
    case 'string':
      return 'info'
    case 'number':
      return 'success'
    case 'boolean':
      return 'warning'
    case 'object':
    case 'array':
      return 'secondary'
    default:
      return 'secondary'
  }
}
</script>

<style scoped>
.variables-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #e5e7eb;
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

.variables-table {
  flex: 1;
}

.variable-name {
  font-weight: 600;
  color: #374151;
  font-family: monospace;
}

.variable-value {
  font-family: monospace;
  font-size: 0.875rem;
  color: #6b7280;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
