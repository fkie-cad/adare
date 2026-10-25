import { AlertTriangle, OctagonAlert } from 'lucide-react'
import { cn } from '@/lib/utils'

export type Severity = 'ok' | 'warning' | 'critical'

export function severityOf(percent: number, warnAt = 80, criticalAt = 92): Severity {
  if (percent >= criticalAt) return 'critical'
  if (percent >= warnAt) return 'warning'
  return 'ok'
}

/** Status reads as icon + word, never color alone. */
export function SeverityLabel({ severity }: { severity: Severity }) {
  if (severity === 'ok') return null
  const Icon = severity === 'critical' ? OctagonAlert : AlertTriangle
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-foreground">
      <Icon
        className={cn('h-3.5 w-3.5', severity === 'critical' ? 'text-status-critical' : 'text-status-warning')}
        aria-hidden
      />
      {severity === 'critical' ? 'Critical' : 'High'}
    </span>
  )
}

interface Segment {
  value: number
  className: string
  label: string
}

interface MeterProps {
  /** 0–100 */
  percent: number
  /** Optional sub-segments of the fill (e.g. ADARE VMs inside used memory), drawn first. */
  segments?: Segment[]
  label: string
  className?: string
}

/**
 * A single ratio against a limit. The fill carries severity (accent → warning →
 * critical); the unfilled track is a lighter step of the same hue.
 */
export function Meter({ percent, segments = [], label, className }: MeterProps) {
  const clamped = Math.max(0, Math.min(100, percent))
  const severity = severityOf(clamped)
  const fill =
    severity === 'critical' ? 'bg-status-critical' : severity === 'warning' ? 'bg-status-warning' : 'bg-series-1'
  const track =
    severity === 'critical' ? 'bg-status-critical/15' : severity === 'warning' ? 'bg-status-warning/20' : 'bg-series-1/15'
  const segmentTotal = segments.reduce((sum, s) => sum + s.value, 0)

  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      className={cn('flex h-2 w-full overflow-hidden rounded-full', track, className)}
    >
      {segments.map((s) => (
        <div
          key={s.label}
          title={s.label}
          className={cn('h-full border-r-2 border-card', s.className)}
          style={{ width: `${Math.max(0, Math.min(100, s.value))}%` }}
        />
      ))}
      <div
        className={cn('h-full rounded-r-full', fill)}
        style={{ width: `${Math.max(0, clamped - segmentTotal)}%` }}
      />
    </div>
  )
}
