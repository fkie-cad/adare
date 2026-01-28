<template>
  <div class="empty-state">
    <i :class="`pi ${icon}`" class="empty-state-icon"></i>
    <h3 class="empty-state-title">{{ title }}</h3>
    <p class="empty-state-message">{{ message }}</p>
    <slot name="actions"></slot>
  </div>
</template>

<script setup lang="ts">
interface Props {
  icon?: string
  title: string
  message: string
}

withDefaults(defineProps<Props>(), {
  icon: 'pi-inbox',
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  text-align: center;
  color: #94a3b8;
}

.empty-state-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-state-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0 0 0.5rem 0;
  color: #64748b;
}

.empty-state-message {
  font-size: 0.95rem;
  margin: 0 0 1.5rem 0;
  max-width: 400px;
  line-height: 1.5;
}
</style>
