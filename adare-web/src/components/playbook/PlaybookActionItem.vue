<template>
  <div
    class="playbook-action-item"
    :class="{
      'selected': isSelected,
      'invalid': isInvalid,
    }"
    @click="$emit('select')"
  >
    <div class="action-header">
      <div class="action-index">{{ index + 1 }}</div>
      <i :class="`pi ${actionIcon}`" class="action-icon"></i>
      <div class="action-info">
        <div class="action-type">{{ action.type }}</div>
        <div class="action-description">{{ actionSummary }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Action } from '@/types/action'

interface Props {
  action: Action
  index: number
  isSelected?: boolean
  isInvalid?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isSelected: false,
  isInvalid: false,
})

defineEmits<{
  select: []
}>()

const actionIcon = computed(() => {
  const iconMap: Record<string, string> = {
    Click: 'pi-mouse-pointer',
    Keyboard: 'pi-keyboard',
    Wait: 'pi-clock',
    Screenshot: 'pi-camera',
    Command: 'pi-terminal',
    Scroll: 'pi-arrows-v',
    Drag: 'pi-arrows-alt',
    Loop: 'pi-refresh',
    Block: 'pi-box',
    Conditional: 'pi-question-circle',
    SetVar: 'pi-pencil',
    FileRead: 'pi-file',
    FileWrite: 'pi-file-edit',
    Test: 'pi-check-circle',
    Checkpoint: 'pi-bookmark',
    RestoreCheckpoint: 'pi-replay',
    Reset: 'pi-undo',
  }
  return iconMap[props.action.type] || 'pi-cog'
})

const actionSummary = computed(() => {
  if (props.action.description) {
    return props.action.description
  }

  // Generate summary based on action type
  switch (props.action.type) {
    case 'Click':
      const clickAction = props.action as any
      const target = clickAction.target?.text || clickAction.target?.image || 'target'
      const button = clickAction.button || 'left'
      return `Click ${target} (${button} click)`

    case 'Keyboard':
      const keyboardAction = props.action as any
      if (keyboardAction.text) {
        return `Type: "${keyboardAction.text}"`
      } else if (keyboardAction.keys) {
        return `Press: ${keyboardAction.keys.join('+')}`
      }
      return 'Type text'

    case 'Wait':
      const waitAction = props.action as any
      if (waitAction.seconds) {
        return `Wait ${waitAction.seconds} seconds`
      } else if (waitAction.condition) {
        return `Wait for condition`
      }
      return 'Wait'

    case 'Screenshot':
      const screenshotAction = props.action as any
      return `Save screenshot: ${screenshotAction.filename || 'screenshot.png'}`

    case 'Command':
      const commandAction = props.action as any
      const cmd = commandAction.command || ''
      return cmd.length > 40 ? `${cmd.substring(0, 40)}...` : cmd

    default:
      return `${props.action.type} action`
  }
})
</script>

<style scoped>
.playbook-action-item {
  background: white;
  border: 2px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.playbook-action-item:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.playbook-action-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.playbook-action-item.invalid {
  border-color: #ef4444;
  background: #fef2f2;
}

.action-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.action-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: #f1f5f9;
  border-radius: 50%;
  font-size: 0.85rem;
  font-weight: 600;
  color: #64748b;
  flex-shrink: 0;
}

.action-icon {
  font-size: 1.25rem;
  color: #64748b;
  flex-shrink: 0;
}

.action-info {
  flex: 1;
  min-width: 0;
}

.action-type {
  font-weight: 600;
  font-size: 0.95rem;
  color: #1e293b;
  margin-bottom: 0.25rem;
}

.action-description {
  font-size: 0.85rem;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
