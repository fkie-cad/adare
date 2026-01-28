<template>
  <component
    :is="formComponent"
    :action="action"
    @update="handleUpdate"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Action } from '@/types/action'
import ClickActionForm from '@/components/actions/ClickActionForm.vue'
import KeyboardActionForm from '@/components/actions/KeyboardActionForm.vue'
import WaitActionForm from '@/components/actions/WaitActionForm.vue'
import ScreenshotActionForm from '@/components/actions/ScreenshotActionForm.vue'
import CommandActionForm from '@/components/actions/CommandActionForm.vue'
import GenericActionForm from '@/components/actions/GenericActionForm.vue'

interface Props {
  action: Action
  actionIndex: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  update: [action: Action]
}>()

const formComponent = computed(() => {
  const formMap: Record<string, any> = {
    Click: ClickActionForm,
    Keyboard: KeyboardActionForm,
    Wait: WaitActionForm,
    Screenshot: ScreenshotActionForm,
    Command: CommandActionForm,
  }

  return formMap[props.action.type] || GenericActionForm
})

function handleUpdate(updatedAction: Action) {
  emit('update', updatedAction)
}
</script>
