/**
 * Playbook store - manages playbook actions and drag-drop state
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { playbookService } from '@/services/playbookService'
import type { Action, ActionTypeMetadata } from '@/types/action'
import { actionService } from '@/services/actionService'
import YAML from 'yaml'

export const usePlaybookStore = defineStore('playbook', () => {
  // State
  const actions = ref<Action[]>([])
  const selectedAction = ref<Action | null>(null)
  const selectedActionIndex = ref<number | null>(null)
  const variables = ref<Record<string, any>>({})
  const playbookName = ref<string>('')
  const isDirty = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const actionTypes = ref<ActionTypeMetadata[]>([])

  // Computed
  const actionCount = computed(() => actions.value.length)
  const hasActions = computed(() => actions.value.length > 0)
  const canSave = computed(() => hasActions.value && playbookName.value.length > 0)

  // Actions
  async function fetchActionTypes() {
    try {
      const response = await actionService.getActionTypes()
      if (response.success && response.data) {
        actionTypes.value = response.data
      }
    } catch (err) {
      console.error('CLAUDE: Failed to fetch action types:', err)
    }
  }

  function addAction(action: Action, index?: number) {
    if (index !== undefined && index >= 0 && index <= actions.value.length) {
      actions.value.splice(index, 0, action)
    } else {
      actions.value.push(action)
    }
    isDirty.value = true
  }

  function removeAction(index: number) {
    if (index >= 0 && index < actions.value.length) {
      actions.value.splice(index, 1)
      isDirty.value = true

      // Clear selection if deleted action was selected
      if (selectedActionIndex.value === index) {
        selectedAction.value = null
        selectedActionIndex.value = null
      }
    }
  }

  function updateAction(index: number, action: Action) {
    if (index >= 0 && index < actions.value.length) {
      actions.value[index] = action
      isDirty.value = true

      // Update selection if updated action is selected
      if (selectedActionIndex.value === index) {
        selectedAction.value = action
      }
    }
  }

  function reorderActions(newOrder: Action[]) {
    actions.value = newOrder
    isDirty.value = true
  }

  function selectAction(index: number) {
    if (index >= 0 && index < actions.value.length) {
      selectedActionIndex.value = index
      selectedAction.value = actions.value[index]
    } else {
      selectedActionIndex.value = null
      selectedAction.value = null
    }
  }

  function clearSelection() {
    selectedActionIndex.value = null
    selectedAction.value = null
  }

  function setVariable(name: string, value: any) {
    variables.value[name] = value
    isDirty.value = true
  }

  function removeVariable(name: string) {
    delete variables.value[name]
    isDirty.value = true
  }

  function clearVariables() {
    variables.value = {}
    isDirty.value = true
  }

  function exportToYAML(): string {
    const playbookData = {
      settings: {
        idle: 3,
        timeout: 30,
      },
      variables: variables.value,
      actions: actions.value,
    }

    return YAML.stringify(playbookData)
  }

  async function savePlaybook(name?: string) {
    const fileName = name || playbookName.value
    if (!fileName) {
      throw new Error('Playbook name is required')
    }

    loading.value = true
    error.value = null

    try {
      const yamlContent = exportToYAML()
      const response = await playbookService.savePlaybook({
        name: fileName,
        content: yamlContent,
      })

      if (response.success) {
        playbookName.value = fileName
        isDirty.value = false
        return response.data
      } else {
        throw new Error(response.error || 'Failed to save playbook')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to save playbook:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function loadPlaybook(name: string) {
    loading.value = true
    error.value = null

    try {
      const response = await playbookService.loadPlaybook(name)

      if (response.success && response.data) {
        const playbookData = YAML.parse(response.data)

        // Load variables
        if (playbookData.variables) {
          variables.value = playbookData.variables
        }

        // Load actions
        if (playbookData.actions && Array.isArray(playbookData.actions)) {
          actions.value = playbookData.actions
        }

        playbookName.value = name
        isDirty.value = false
      } else {
        throw new Error(response.error || 'Failed to load playbook')
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error'
      console.error('CLAUDE: Failed to load playbook:', error.value)
      throw err
    } finally {
      loading.value = false
    }
  }

  function clearPlaybook() {
    actions.value = []
    variables.value = {}
    playbookName.value = ''
    selectedAction.value = null
    selectedActionIndex.value = null
    isDirty.value = false
  }

  return {
    // State
    actions,
    selectedAction,
    selectedActionIndex,
    variables,
    playbookName,
    isDirty,
    loading,
    error,
    actionTypes,

    // Computed
    actionCount,
    hasActions,
    canSave,

    // Actions
    fetchActionTypes,
    addAction,
    removeAction,
    updateAction,
    reorderActions,
    selectAction,
    clearSelection,
    setVariable,
    removeVariable,
    clearVariables,
    exportToYAML,
    savePlaybook,
    loadPlaybook,
    clearPlaybook,
  }
})
