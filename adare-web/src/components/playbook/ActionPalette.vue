<template>
  <div class="action-palette">
    <h2>Actions</h2>

    <div class="search-box">
      <span class="p-input-icon-left" style="width: 100%">
        <i class="pi pi-search"></i>
        <InputText
          v-model="searchQuery"
          placeholder="Search actions..."
          class="search-input"
        />
      </span>
    </div>

    <Accordion :multiple="true" :activeIndex="[0, 1, 2, 3]">
      <AccordionTab
        v-for="category in filteredCategories"
        :key="category.name"
        :header="category.name"
      >
        <div class="action-list">
          <ActionPaletteItem
            v-for="actionType in category.actions"
            :key="actionType.type"
            :action-type="actionType"
            @add="handleAddAction"
          />
        </div>
      </AccordionTab>
    </Accordion>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePlaybookStore } from '@/stores/playbookStore'
import type { ActionTypeMetadata } from '@/types/action'
import InputText from 'primevue/inputtext'
import Accordion from 'primevue/accordion'
import AccordionTab from 'primevue/accordiontab'
import ActionPaletteItem from './ActionPaletteItem.vue'

const playbookStore = usePlaybookStore()
const searchQuery = ref('')

interface ActionCategory {
  name: string
  actions: ActionTypeMetadata[]
}

// Define categories and their actions
const categories = computed<ActionCategory[]>(() => {
  const actionsByCategory: Record<string, ActionTypeMetadata[]> = {
    gui: [],
    control: [],
    data: [],
    system: [],
  }

  // Group actions by category
  playbookStore.actionTypes.forEach((actionType) => {
    const category = actionType.category || 'system'
    if (actionsByCategory[category]) {
      actionsByCategory[category].push(actionType)
    }
  })

  return [
    { name: 'GUI Actions', actions: actionsByCategory.gui },
    { name: 'Control Flow', actions: actionsByCategory.control },
    { name: 'Data Actions', actions: actionsByCategory.data },
    { name: 'System Actions', actions: actionsByCategory.system },
  ]
})

const filteredCategories = computed(() => {
  if (!searchQuery.value.trim()) {
    return categories.value
  }

  const query = searchQuery.value.toLowerCase()
  return categories.value
    .map((category) => ({
      ...category,
      actions: category.actions.filter(
        (action) =>
          action.display_name.toLowerCase().includes(query) ||
          action.description.toLowerCase().includes(query) ||
          action.type.toLowerCase().includes(query)
      ),
    }))
    .filter((category) => category.actions.length > 0)
})

function handleAddAction(actionType: ActionTypeMetadata) {
  // Create a new action with default parameters
  const newAction: any = {
    type: actionType.type,
    ...actionType.default_params,
  }

  playbookStore.addAction(newAction)
  console.log(`CLAUDE: Added ${actionType.type} action to playbook`)
}

onMounted(() => {
  // Fetch action types if not already loaded
  if (playbookStore.actionTypes.length === 0) {
    playbookStore.fetchActionTypes()
  }
})
</script>

<style scoped>
.action-palette {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.action-palette h2 {
  font-size: 1rem;
  margin: 0 0 1rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e2e8f0;
}

.search-box {
  margin-bottom: 1rem;
}

.search-input {
  width: 100%;
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

:deep(.p-accordion) {
  flex: 1;
  overflow-y: auto;
}

:deep(.p-accordion-header-link) {
  padding: 0.75rem 1rem;
  font-weight: 600;
  font-size: 0.9rem;
}

:deep(.p-accordion-content) {
  padding: 0.5rem 1rem;
}
</style>
