import { create } from 'zustand'
import { stringify } from 'yaml'
import type { Action, ActionTypeMetadata } from '@/types/action'

interface PlaybookState {
  actions: Action[]
  selectedActionIndex: number | null
  variables: Record<string, unknown>
  playbookName: string
  isDirty: boolean
  actionTypes: ActionTypeMetadata[]

  setActionTypes: (types: ActionTypeMetadata[]) => void
  addAction: (action: Action, index?: number) => void
  removeAction: (index: number) => void
  updateAction: (index: number, action: Action) => void
  reorderActions: (newOrder: Action[]) => void
  selectAction: (index: number | null) => void
  setVariable: (name: string, value: unknown) => void
  removeVariable: (name: string) => void
  clearVariables: () => void
  exportToYAML: () => string
  clearPlaybook: () => void
  setPlaybookName: (name: string) => void
  markClean: () => void
}

export const usePlaybookStore = create<PlaybookState>((set, get) => ({
  actions: [],
  selectedActionIndex: null,
  variables: {},
  playbookName: 'untitled',
  isDirty: false,
  actionTypes: [],

  setActionTypes: (types) => set({ actionTypes: types }),

  addAction: (action, index) =>
    set((state) => {
      const actions = [...state.actions]
      if (index !== undefined) {
        actions.splice(index, 0, action)
      } else {
        actions.push(action)
      }
      return { actions, isDirty: true }
    }),

  removeAction: (index) =>
    set((state) => {
      const actions = state.actions.filter((_, i) => i !== index)
      const selectedActionIndex =
        state.selectedActionIndex === index ? null : state.selectedActionIndex
      return { actions, selectedActionIndex, isDirty: true }
    }),

  updateAction: (index, action) =>
    set((state) => {
      const actions = [...state.actions]
      actions[index] = action
      return { actions, isDirty: true }
    }),

  reorderActions: (newOrder) => set({ actions: newOrder, isDirty: true }),

  selectAction: (index) => set({ selectedActionIndex: index }),

  setVariable: (name, value) =>
    set((state) => ({
      variables: { ...state.variables, [name]: value },
    })),

  removeVariable: (name) =>
    set((state) => {
      const { [name]: _, ...rest } = state.variables
      return { variables: rest }
    }),

  clearVariables: () => set({ variables: {} }),

  exportToYAML: () => {
    const { actions, variables } = get()
    return stringify({ actions, variables })
  },

  clearPlaybook: () =>
    set({
      actions: [],
      selectedActionIndex: null,
      variables: {},
      playbookName: 'untitled',
      isDirty: false,
    }),

  setPlaybookName: (name) => set({ playbookName: name }),
  markClean: () => set({ isDirty: false }),
}))
