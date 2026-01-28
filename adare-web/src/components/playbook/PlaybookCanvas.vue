<template>
  <div
    class="playbook-canvas"
    @drop="handleDrop"
    @dragover.prevent
    @dragenter.prevent
  >
    <h2>Playbook Canvas</h2>

    <EmptyState
      v-if="!playbookStore.hasActions"
      icon="pi-inbox"
      title="No Actions Yet"
      message="Drag actions from the left palette to build your playbook"
    />

    <draggable
      v-else
      :list="actions"
      :item-key="(item: any, index: number) => index"
      handle=".drag-handle"
      class="actions-list"
      @end="handleReorder"
    >
      <template #item="{ element, index }">
        <div class="action-wrapper">
          <div class="drag-handle">
            <i class="pi pi-bars"></i>
          </div>
          <PlaybookActionItem
            :action="element"
            :index="index"
            :is-selected="playbookStore.selectedActionIndex === index"
            @select="handleSelectAction(index)"
          />
          <div class="action-controls">
            <Button
              icon="pi pi-trash"
              severity="danger"
              text
              rounded
              size="small"
              @click="handleDelete(index)"
            />
          </div>
        </div>
      </template>
    </draggable>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePlaybookStore } from '@/stores/playbookStore'
import { useToast } from 'primevue/usetoast'
import type { ActionTypeMetadata } from '@/types/action'
import draggable from 'vuedraggable'
import Button from 'primevue/button'
import PlaybookActionItem from './PlaybookActionItem.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const playbookStore = usePlaybookStore()
const toast = useToast()

// Two-way computed property for vuedraggable
const actions = computed({
  get: () => playbookStore.actions,
  set: (value) => {
    playbookStore.reorderActions(value)
  },
})

function handleSelectAction(index: number) {
  playbookStore.selectAction(index)
}

function handleDrop(event: DragEvent) {
  event.preventDefault()

  const data = event.dataTransfer?.getData('application/json')
  if (!data) return

  try {
    const actionType: ActionTypeMetadata = JSON.parse(data)

    // Create new action with default params
    const newAction: any = {
      type: actionType.type,
      ...actionType.default_params,
    }

    playbookStore.addAction(newAction)
    console.log(`CLAUDE: Dropped ${actionType.type} action to canvas`)

    toast.add({
      severity: 'success',
      summary: 'Action Added',
      detail: `${actionType.display_name} added to playbook`,
      life: 2000,
    })
  } catch (err) {
    console.error('CLAUDE: Failed to parse dropped action:', err)
  }
}

function handleReorder() {
  console.log('CLAUDE: Actions reordered')
}

function handleDelete(index: number) {
  const action = playbookStore.actions[index]
  playbookStore.removeAction(index)

  toast.add({
    severity: 'info',
    summary: 'Action Removed',
    detail: `${action.type} action removed`,
    life: 2000,
  })
}
</script>

<style scoped>
.playbook-canvas {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.playbook-canvas h2 {
  font-size: 1rem;
  margin: 0 0 1rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e2e8f0;
}

.actions-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.25rem 0;
}

.action-wrapper {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: #94a3b8;
  cursor: grab;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.action-wrapper:hover .drag-handle {
  opacity: 1;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle i {
  font-size: 1rem;
}

.action-wrapper > :nth-child(2) {
  flex: 1;
  min-width: 0;
}

.action-controls {
  display: flex;
  gap: 0.25rem;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.action-wrapper:hover .action-controls {
  opacity: 1;
}
</style>
