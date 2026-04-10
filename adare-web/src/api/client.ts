import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  config.params = { ...config.params, _t: Date.now() }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const data = error.response?.data
    const message = data?.error ?? data?.message ?? data?.detail ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  },
)
