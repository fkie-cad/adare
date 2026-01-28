<template>
  <div class="action-config-panel">
    <h2>Configuration</h2>

    <EmptyState
      v-if="!playbookStore.selectedAction"
      icon="pi-cog"
      title="No Action Selected"
      message="Click an action in the canvas to configure its parameters"
    />

    <TabView v-else>
      <TabPanel header="Action Config">
        <ActionConfigForm
          :action="playbookStore.selectedAction"
          :action-index="playbookStore.selectedActionIndex!"
          @update="handleUpdate"
        />
      </TabPanel>

      <TabPanel header="Settings">
        <div class="form-group">
          <label for="description">Description</label>
          <InputText
            id="description"
            v-model="description"
            placeholder="Optional action description"
            @input="handleDescriptionUpdate"
          />
        </div>

        <div class="form-group">
          <label>
            <Checkbox v-model="screenshotBefore" binary @change="handleScreenshotBeforeUpdate" />
            Screenshot Before
          </label>
        </div>

        <div class="form-group">
          <label>
            <Checkbox v-model="screenshotAfter" binary @change="handleScreenshotAfterUpdate" />
            Screenshot After
          </label>
        </div>
      </TabPanel>

      <TabPanel header="Variables">
        <div class="variables-help">
          <p>Available variables:</p>
          <ul v-if="Object.keys(playbookStore.variables).length > 0">
            <li v-for="(value, name) in playbookStore.variables" :key="name">
              <code>{{ `{{${name}}}` }}</code> = {{ value }}
            </li>
          </ul>
          <p v-else class="empty-text">No variables defined yet</p>
        </div>
      </TabPanel>
    </TabView>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePlaybookStore } from '@/stores/playbookStore'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import InputText from 'primevue/inputtext'
import Checkbox from 'primevue/checkbox'
import EmptyState from '@/components/common/EmptyState.vue'
import ActionConfigForm from './ActionConfigForm.vue'

const playbookStore = usePlaybookStore()

const description = ref('')
const screenshotBefore = ref(false)
const screenshotAfter = ref(false)

// Watch for action selection changes
watch(
  () => playbookStore.selectedAction,
  (newAction) => {
    if (newAction) {
      description.value = newAction.description || ''
      screenshotBefore.value = newAction.screenshot_before || false
      screenshotAfter.value = newAction.screenshot_after || false
    }
  },
  { immediate: true }
)

function handleUpdate(updatedAction: any) {
  if (playbookStore.selectedActionIndex !== null) {
    playbookStore.updateAction(playbookStore.selectedActionIndex, updatedAction)
  }
}

function handleDescriptionUpdate() {
  if (playbookStore.selectedAction && playbookStore.selectedActionIndex !== null) {
    const updated = { ...playbookStore.selectedAction, description: description.value }
    playbookStore.updateAction(playbookStore.selectedActionIndex, updated)
  }
}

function handleScreenshotBeforeUpdate() {
  if (playbookStore.selectedAction && playbookStore.selectedActionIndex !== null) {
    const updated = { ...playbookStore.selectedAction, screenshot_before: screenshotBefore.value }
    playbookStore.updateAction(playbookStore.selectedActionIndex, updated)
  }
}

function handleScreenshotAfterUpdate() {
  if (playbookStore.selectedAction && playbookStore.selectedActionIndex !== null) {
    const updated = { ...playbookStore.selectedAction, screenshot_after: screenshotAfter.value }
    playbookStore.updateAction(playbookStore.selectedActionIndex, updated)
  }
}
</script>

<style scoped>
.action-config-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.action-config-panel h2 {
  font-size: 1rem;
  margin: 0 0 1rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e2e8f0;
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

.form-group input[type='text'],
.form-group textarea,
.form-group select {
  width: 100%;
}

.variables-help {
  padding: 1rem;
  background: #f8fafc;
  border-radius: 0.375rem;
  font-size: 0.9rem;
}

.variables-help p {
  margin: 0 0 0.5rem 0;
  font-weight: 500;
}

.variables-help ul {
  margin: 0;
  padding-left: 1.5rem;
}

.variables-help li {
  margin-bottom: 0.5rem;
}

.variables-help code {
  background: #e2e8f0;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-family: monospace;
  font-size: 0.85rem;
}

.empty-text {
  color: #94a3b8;
  font-style: italic;
}
</style>
