/**
 * Vue Router configuration
 */

import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomePage.vue'),
    },
    {
      path: '/sessions',
      name: 'sessions',
      component: () => import('@/views/SessionsPage.vue'),
    },
    {
      path: '/session/:id',
      name: 'dev-session',
      component: () => import('@/views/DevSessionPage.vue'),
      props: true,
    },
    {
      path: '/playbook/editor',
      name: 'playbook-editor',
      component: () => import('@/views/PlaybookEditorPage.vue'),
    },
  ],
})

export default router
