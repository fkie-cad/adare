/**
 * Main entry point for ADARE Web frontend
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'

import App from './App.vue'
import router from './router'

// PrimeVue CSS
import 'primevue/resources/themes/lara-dark-blue/theme.css'
import 'primevue/resources/primevue.min.css'
import 'primeicons/primeicons.css'

// Global styles
import './assets/main.css'

const app = createApp(App)

// Install plugins
app.use(createPinia())
app.use(router)
app.use(PrimeVue)
app.use(ToastService)

// Mount app
app.mount('#app')

console.log('CLAUDE: ADARE Web frontend initialized')
