<template>
  <div
    class="action-palette-item"
    draggable="true"
    @click="handleClick"
    @dragstart="handleDragStart"
    @dragend="handleDragEnd"
  >
    <i :class="`pi ${actionType.icon}`" class="action-icon"></i>
    <div class="action-details">
      <div class="action-name">{{ actionType.display_name }}</div>
      <div class="action-desc">{{ actionType.description }}</div>
    </div>
    <i class="pi pi-plus add-icon"></i>
  </div>
</template>

<script setup lang="ts">
import type { ActionTypeMetadata } from '@/types/action'

interface Props {
  actionType: ActionTypeMetadata
}

const props = defineProps<Props>()

const emit = defineEmits<{
  add: [actionType: ActionTypeMetadata]
}>()

function handleClick() {
  emit('add', props.actionType)
}

function handleDragStart(event: DragEvent) {
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('application/json', JSON.stringify(props.actionType))
  }
}

function handleDragEnd(event: DragEvent) {
  // Cleanup if needed
}
</script>

<style scoped>
.action-palette-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  cursor: grab;
  transition: all 0.2s ease;
}

.action-palette-item:active {
  cursor: grabbing;
}

.action-palette-item:hover {
  border-color: #3b82f6;
  background: #f8fafc;
  transform: translateX(2px);
}

.action-icon {
  font-size: 1.25rem;
  color: #3b82f6;
  flex-shrink: 0;
}

.action-details {
  flex: 1;
  min-width: 0;
}

.action-name {
  font-weight: 600;
  font-size: 0.9rem;
  color: #1e293b;
  margin-bottom: 0.25rem;
}

.action-desc {
  font-size: 0.8rem;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.3;
}

.add-icon {
  font-size: 1rem;
  color: #94a3b8;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.action-palette-item:hover .add-icon {
  opacity: 1;
}
</style>
