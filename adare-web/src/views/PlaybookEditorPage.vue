<template>
  <div class="playbook-editor-page">
    <div class="page-header">
      <div class="header-left">
        <h1>Playbook Editor</h1>
        <InputText
          v-model="playbookStore.playbookName"
          placeholder="playbook-name"
          class="playbook-name-input"
        />
        <span v-if="playbookStore.isDirty" class="dirty-indicator">
          <i class="pi pi-circle-fill"></i>
          Unsaved
        </span>
      </div>
      <div class="header-actions">
        <Button label="New" icon="pi pi-file" @click="handleNew" />
        <Button label="Load" icon="pi pi-folder-open" @click="handleLoad" />
        <Button
          label="Save"
          icon="pi pi-save"
          :disabled="!playbookStore.canSave"
          @click="handleSave"
        />
        <Button label="Export" icon="pi pi-download" @click="handleExport" />
      </div>
    </div>

    <div class="editor-layout">
      <div class="editor-palette">
        <ActionPalette />
      </div>

      <div class="editor-main">
        <PlaybookCanvas />
      </div>

      <div class="editor-sidebar">
        <ActionConfigPanel />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { usePlaybookStore } from '@/stores/playbookStore'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import ActionPalette from '@/components/playbook/ActionPalette.vue'
import PlaybookCanvas from '@/components/playbook/PlaybookCanvas.vue'
import ActionConfigPanel from '@/components/playbook/ActionConfigPanel.vue'

const playbookStore = usePlaybookStore()
const toast = useToast()

// Keyboard shortcuts
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})

function handleKeyDown(event: KeyboardEvent) {
  // Ctrl+S or Cmd+S to save
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault()
    if (playbookStore.canSave) {
      handleSave()
    }
  }

  // Delete key to remove selected action
  if (event.key === 'Delete' && playbookStore.selectedActionIndex !== null) {
    event.preventDefault()
    playbookStore.removeAction(playbookStore.selectedActionIndex)
    toast.add({
      severity: 'info',
      summary: 'Action Removed',
      detail: 'Selected action deleted',
      life: 2000,
    })
  }
}

function handleNew() {
  if (playbookStore.isDirty) {
    if (!confirm('You have unsaved changes. Create new playbook anyway?')) {
      return
    }
  }

  playbookStore.clearPlaybook()
  toast.add({
    severity: 'success',
    summary: 'New Playbook',
    detail: 'Created new playbook',
    life: 3000,
  })
}

function handleLoad() {
  const name = prompt('Enter playbook name to load:')
  if (!name) return

  playbookStore
    .loadPlaybook(name)
    .then(() => {
      toast.add({
        severity: 'success',
        summary: 'Playbook Loaded',
        detail: `Loaded playbook: ${name}`,
        life: 3000,
      })
    })
    .catch((err) => {
      toast.add({
        severity: 'error',
        summary: 'Load Failed',
        detail: err.message || 'Failed to load playbook',
        life: 5000,
      })
    })
}

async function handleSave() {
  if (!playbookStore.playbookName) {
    toast.add({
      severity: 'warn',
      summary: 'Name Required',
      detail: 'Please enter a playbook name',
      life: 3000,
    })
    return
  }

  try {
    await playbookStore.savePlaybook()
    toast.add({
      severity: 'success',
      summary: 'Playbook Saved',
      detail: `Saved as: ${playbookStore.playbookName}`,
      life: 3000,
    })
  } catch (err: any) {
    toast.add({
      severity: 'error',
      summary: 'Save Failed',
      detail: err.message || 'Failed to save playbook',
      life: 5000,
    })
  }
}

function handleExport() {
  const yaml = playbookStore.exportToYAML()
  console.log('CLAUDE: Exported YAML:', yaml)

  // Create download link
  const blob = new Blob([yaml], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${playbookStore.playbookName || 'playbook'}.yaml`
  a.click()
  URL.revokeObjectURL(url)

  toast.add({
    severity: 'success',
    summary: 'Export Complete',
    detail: 'Playbook exported as YAML file',
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

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.page-header h1 {
  margin: 0;
  font-size: 1.25rem;
}

.playbook-name-input {
  width: 250px;
}

.dirty-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #f59e0b;
  font-size: 0.9rem;
  font-weight: 500;
}

.dirty-indicator i {
  font-size: 0.5rem;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.editor-layout {
  display: grid;
  grid-template-columns: 250px 1fr 350px;
  gap: 1rem;
  padding: 1rem;
  height: calc(100% - 80px);
  overflow: hidden;
}

.editor-palette,
.editor-main,
.editor-sidebar {
  background: white;
  border-radius: 0.5rem;
  padding: 1rem;
  overflow-y: auto;
}

</style>
