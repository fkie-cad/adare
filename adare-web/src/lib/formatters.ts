/**
 * Pure utility formatters — no React, no side effects, never throw.
 */

/**
 * Parse an ISO-ish timestamp (string, number, Date, null, undefined) and
 * return a local "YYYY-MM-DD HH:mm" string, or "—" for anything invalid.
 */
export function formatDateTime(value: unknown): string {
  if (value == null) return '—'
  let d: Date
  if (value instanceof Date) {
    d = value
  } else if (typeof value === 'number') {
    // Heuristic: epoch-seconds have ~10 digits, epoch-ms ~13 digits
    const ms = value < 1e12 ? value * 1000 : value
    d = new Date(ms)
  } else if (typeof value === 'string') {
    if (value.trim() === '') return '—'
    d = new Date(value)
  } else {
    return '—'
  }
  if (isNaN(d.getTime())) return '—'

  const pad = (n: number) => String(n).padStart(2, '0')
  const year = d.getFullYear()
  const month = pad(d.getMonth() + 1)
  const day = pad(d.getDate())
  const hours = pad(d.getHours())
  const minutes = pad(d.getMinutes())
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

/**
 * Return a human-readable relative time string, e.g. "2 minutes ago",
 * "just now", "3 days ago", or "—" for null/undefined/invalid input.
 */
export function formatRelativeTime(value: unknown): string {
  if (value == null) return '—'
  let d: Date
  if (value instanceof Date) {
    d = value
  } else if (typeof value === 'number') {
    const ms = value < 1e12 ? value * 1000 : value
    d = new Date(ms)
  } else if (typeof value === 'string') {
    if (value.trim() === '') return '—'
    d = new Date(value)
  } else {
    return '—'
  }
  if (isNaN(d.getTime())) return '—'

  const diffMs = Date.now() - d.getTime()
  const diffSec = Math.round(diffMs / 1000)
  if (Math.abs(diffSec) < 10) return 'just now'
  if (Math.abs(diffSec) < 60) return `${diffSec} seconds ago`
  const diffMin = Math.round(diffSec / 60)
  if (Math.abs(diffMin) < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`
  const diffHr = Math.round(diffMin / 60)
  if (Math.abs(diffHr) < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`
  const diffDay = Math.round(diffHr / 24)
  return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`
}

/**
 * Humanize a duration in seconds.
 *   < 60s  → "Xs"        e.g. "45s"
 *   < 1h   → "Xm [Ys]"  e.g. "2m 15s" (seconds omitted if zero: "2m")
 *   ≥ 1h   → "Xh [Ym]"  (minutes omitted if zero: "3h")
 *   invalid → "—"
 */
export function formatDuration(seconds: unknown): string {
  if (seconds == null) return '—'
  const s = typeof seconds === 'number' ? seconds : Number(seconds)
  if (!isFinite(s) || isNaN(s) || s < 0) return '—'

  const totalSec = Math.round(s)
  if (totalSec < 60) return `${totalSec}s`

  const mins = Math.floor(totalSec / 60)
  const secs = totalSec % 60
  if (mins < 60) {
    return secs === 0 ? `${mins}m` : `${mins}m ${secs}s`
  }

  const hours = Math.floor(mins / 60)
  const remMins = mins % 60
  return remMins === 0 ? `${hours}h` : `${hours}h ${remMins}m`
}

/**
 * Format a count with a singular/plural label.
 * e.g. formatCount(3, 'run') → '3 runs'; formatCount(1, 'run') → '1 run'
 * Handles null/undefined → "0 <plural>".
 */
export function formatCount(value: unknown, singular: string, plural?: string): string {
  const n = value == null ? 0 : Number(value)
  const count = isNaN(n) ? 0 : Math.round(n)
  const label = count === 1 ? singular : (plural ?? `${singular}s`)
  return `${count} ${label}`
}
