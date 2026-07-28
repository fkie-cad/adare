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

/** Pull a human-readable message out of whatever shape the failure arrived in.
 *
 * `error` is an OBJECT (`{code, message, solutions}`) on every route that goes
 * through the backend's `result_to_response`, so treating it as a string produced
 * "[object Object]". A plain string is still accepted in case a hand-rolled route
 * sends one.
 */
function extractMessage(error: unknown): string | null {
  if (typeof error === 'string') return error || null
  if (!error || typeof error !== 'object') return null
  const { code, message } = error as { code?: string; message?: string }
  return message ?? code ?? null
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only reached for 4xx/5xx and transport failures. Note that a *contract*
    // rejection from the webapi arrives as HTTP 200 with `success: false`, so it
    // never gets here — hooks must check `data.success` themselves.
    const data = error.response?.data
    const message =
      extractMessage(data?.error) ??
      data?.message ??
      data?.detail ??
      error.message ??
      'Unknown error'
    return Promise.reject(new Error(message))
  },
)
