import { useState } from 'react'
import { cn } from '@/lib/utils'

export interface StackSegment {
  key: string
  label: string
  value: number
  /** Tailwind background class of a series token, e.g. `bg-series-1` */
  colorClass: string
  detail?: string
}

interface StackedBarProps {
  segments: StackSegment[]
  total: number
  format: (value: number) => string
  /** Label for the unfilled remainder (e.g. "Free"); omitted when the segments are the whole. */
  remainderLabel?: string
}

/**
 * Part-to-whole as one horizontal bar: 2px surface gaps between segments, a
 * hover/focus tooltip per segment, and a legend that doubles as the table view
 * (every value is readable without hovering).
 */
export function StackedBar({ segments, total, format, remainderLabel }: StackedBarProps) {
  const [active, setActive] = useState<string | null>(null)
  const visible = segments.filter((s) => s.value > 0)
  const used = visible.reduce((sum, s) => sum + s.value, 0)
  const remainder = Math.max(total - used, 0)
  const pct = (v: number) => (total > 0 ? (100 * v) / total : 0)
  const activeSegment = visible.find((s) => s.key === active)

  return (
    <div className="space-y-3">
      <div className="relative">
        <div className="flex h-6 w-full gap-[2px] overflow-hidden rounded-md bg-muted">
          {visible.map((s) => (
            <button
              type="button"
              key={s.key}
              aria-label={`${s.label}: ${format(s.value)}`}
              className={cn(
                'h-full min-w-[3px] transition-opacity first:rounded-l-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                s.colorClass,
                active && active !== s.key && 'opacity-50',
              )}
              style={{ width: `${pct(s.value)}%` }}
              onPointerEnter={() => setActive(s.key)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(s.key)}
              onBlur={() => setActive(null)}
            />
          ))}
        </div>
        {activeSegment && (
          <div className="pointer-events-none absolute left-0 top-8 z-10 rounded-md border bg-popover px-3 py-2 text-sm shadow-md">
            <div className="font-semibold">{format(activeSegment.value)}</div>
            <div className="text-muted-foreground">
              {activeSegment.label} · {pct(activeSegment.value).toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      <ul className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
        {visible.map((s) => (
          <li
            key={s.key}
            className={cn('flex items-center gap-2 rounded px-1', active === s.key && 'bg-muted')}
            onPointerEnter={() => setActive(s.key)}
            onPointerLeave={() => setActive(null)}
          >
            <span className={cn('h-2.5 w-2.5 shrink-0 rounded-sm', s.colorClass)} aria-hidden />
            <span className="min-w-0 flex-1 truncate" title={s.detail}>
              {s.label}
            </span>
            <span className="tabular-nums font-medium">{format(s.value)}</span>
          </li>
        ))}
        {remainderLabel && (
          <li className="flex items-center gap-2 px-1">
            <span className="h-2.5 w-2.5 shrink-0 rounded-sm bg-muted ring-1 ring-border" aria-hidden />
            <span className="flex-1 text-muted-foreground">{remainderLabel}</span>
            <span className="tabular-nums text-muted-foreground">{format(remainder)}</span>
          </li>
        )}
      </ul>
    </div>
  )
}
