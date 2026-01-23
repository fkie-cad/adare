<template>
  <div id="app" class="app-container">
    <header class="app-header">
      <div class="header-left">
        <h1 class="app-title">ADARE Web</h1>
        <span class="app-subtitle">Automated Desktop Analysis</span>
      </div>
      <nav class="header-nav">
        <router-link to="/" class="nav-link">Home</router-link>
        <router-link to="/sessions" class="nav-link">Sessions</router-link>
        <router-link to="/playbook/editor" class="nav-link">Playbook Editor</router-link>
      </nav>
      <div class="header-right">
        <span v-if="isConnected" class="status-indicator connected">Connected</span>
        <span v-else class="status-indicator disconnected">Disconnected</span>
      </div>
    </header>

    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <Toast position="bottom-right" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSessionStore } from '@/stores/sessionStore'
import Toast from 'primevue/toast'

const sessionStore = useSessionStore()

const isConnected = computed(() => sessionStore.isConnected)

onMounted(() => {
  // Fetch sessions on app load
  sessionStore.fetchSessions()
})
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  background: #1e293b;
  color: white;
  border-bottom: 2px solid #334155;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 1rem;
}

.app-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: bold;
}

.app-subtitle {
  font-size: 0.875rem;
  color: #94a3b8;
}

.header-nav {
  display: flex;
  gap: 1.5rem;
}

.nav-link {
  color: #cbd5e1;
  text-decoration: none;
  padding: 0.5rem 1rem;
  border-radius: 0.25rem;
  transition: all 0.2s;
}

.nav-link:hover {
  background: #334155;
  color: white;
}

.nav-link.router-link-active {
  background: #3b82f6;
  color: white;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  border-radius: 0.25rem;
  font-size: 0.875rem;
}

.status-indicator::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-indicator.connected {
  background: #064e3b;
  color: #6ee7b7;
}

.status-indicator.connected::before {
  background: #10b981;
}

.status-indicator.disconnected {
  background: #450a0a;
  color: #fca5a5;
}

.status-indicator.disconnected::before {
  background: #ef4444;
}

.app-main {
  flex: 1;
  overflow: auto;
  background: #f8fafc;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
