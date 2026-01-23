<template>
  <div class="playbook-editor-page">
    <div class="page-header">
      <h1>Playbook Editor</h1>
      <div class="header-actions">
        <Button label="New Playbook" icon="pi pi-file" @click="handleNew" />
        <Button label="Load Playbook" icon="pi pi-folder-open" @click="handleLoad" />
        <Button
          label="Save Playbook"
          icon="pi pi-save"
          :disabled="!playbookStore.canSave"
          @click="handleSave"
        />
        <Button label="Export YAML" icon="pi pi-download" @click="handleExport" />
      </div>
    </div>

    <div class="editor-layout">
      <div class="editor-main">
        <div class="playbook-canvas">
          <h2>Playbook Canvas</h2>
          <p class="placeholder">
            Drag-and-drop action builder will be implemented in Phase 4
          </p>
          <p class="info">Current actions: {{ playbookStore.actionCount }}</p>
        </div>
      </div>

      <div class="editor-sidebar">
        <div class="settings-panel">
          <h2>Settings</h2>
          <div class="form-group">
            <label for="playbook-name">Playbook Name</label>
            <InputText
              id="playbook-name"
              v-model="playbookStore.playbookName"
              placeholder="my-playbook"
            />
          </div>
          <p class="placeholder">More settings will be added here</p>
        </div>

        <div class="variables-panel">
          <h2>Variables</h2>
          <p class="placeholder">Variable manager will be implemented in Phase 4</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { usePlaybookStore } from '@/stores/playbookStore'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'

const playbookStore = usePlaybookStore()
const toast = useToast()

function handleNew() {
  playbookStore.clearPlaybook()
  toast.add({
    severity: 'success',
    summary: 'New Playbook',
    detail: 'Created new playbook',
    life: 3000,
  })
}

function handleLoad() {
  toast.add({
    severity: 'info',
    summary: 'Not Implemented',
    detail: 'Load functionality will be implemented in Phase 4',
    life: 3000,
  })
}

function handleSave() {
  toast.add({
    severity: 'info',
    summary: 'Not Implemented',
    detail: 'Save functionality will be implemented in Phase 4',
    life: 3000,
  })
}

function handleExport() {
  const yaml = playbookStore.exportToYAML()
  console.log('CLAUDE: Exported YAML:', yaml)
  toast.add({
    severity: 'info',
    summary: 'Export',
    detail: 'YAML exported to console (full export UI coming in Phase 4)',
    life: 3000,
  })
}
</script>

<style scoped>
.playbook-editor-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.page-header h1 {
  margin: 0;
  font-size: 1.25rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.editor-layout {
  display: grid;
  grid-template-columns: 1fr 350px;
  gap: 1rem;
  padding: 1rem;
  height: calc(100% - 80px);
  overflow: hidden;
}

.editor-main,
.editor-sidebar {
  background: white;
  border-radius: 0.5rem;
  padding: 1rem;
  overflow-y: auto;
}

.playbook-canvas h2,
.settings-panel h2,
.variables-panel h2 {
  font-size: 1rem;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e2e8f0;
}

.placeholder {
  color: #94a3b8;
  font-style: italic;
  margin: 1rem 0;
  padding: 1rem;
  background: #f1f5f9;
  border-radius: 0.25rem;
}

.info {
  color: #64748b;
  margin-top: 1rem;
}

.settings-panel,
.variables-panel {
  margin-bottom: 1.5rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.form-group input {
  width: 100%;
}
</style>
