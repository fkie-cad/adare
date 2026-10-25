import { useEffect, useMemo, useRef, useState } from 'react'

export interface Series {
  key: string
  label: string
  /** CSS color, normally a series token: `var(--color-series-1)` */
  color: string
  values: number[]
}

interface TimeSeriesChartProps {
  times: Date[]
  series: Series[]
  formatValue: (value: number) => string
  /** Fixed top of the y-scale (e.g. 100 for percent, total RAM for memory); otherwise the data max. */
  yMax?: number
  /** Counts: gridlines land on whole numbers. */
  integer?: boolean
  height?: number
  ariaLabel: string
}

const PAD = { top: 8, right: 12, bottom: 22, left: 56 }
const GRID_LINES = 4
const MIN_TICK_GAP = 70

function timeLabel(d: Date, spanMs: number): string {
  if (spanMs > 2 * 86400000) return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

/**
 * Lines over time on one y-axis, with a crosshair that snaps to the nearest
 * sample and one tooltip listing every series. A single series gets a 10% area
 * wash; two or more get a legend (identity is never color alone).
 */
export function TimeSeriesChart({
  times,
  series,
  formatValue,
  yMax,
  integer = false,
  height = 180,
  ariaLabel,
}: TimeSeriesChartProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(entry.contentRect.width, 200)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const n = times.length
  const innerW = width - PAD.left - PAD.right
  const innerH = height - PAD.top - PAD.bottom
  const top = useMemo(() => {
    const dataMax = Math.max(0, ...series.flatMap((s) => s.values))
    if (yMax) return yMax
    if (integer) return Math.max(GRID_LINES, Math.ceil(dataMax / GRID_LINES) * GRID_LINES)
    return dataMax > 0 ? dataMax * 1.1 : 1
  }, [series, yMax, integer])
  const t0 = n ? times[0].getTime() : 0
  const span = n > 1 ? times[n - 1].getTime() - t0 : 1
  const x = (i: number) => PAD.left + (n > 1 ? ((times[i].getTime() - t0) / span) * innerW : innerW / 2)
  const y = (v: number) => PAD.top + innerH - (Math.min(v, top) / top) * innerH

  const path = (values: number[]) => values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join('')

  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!n) return
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left
    let best = 0
    for (let i = 1; i < n; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i
    setHover(best)
  }

  // Start, middle and end, dropping any that would collide with the one before
  const xTicks = (n > 1 ? [0, Math.floor((n - 1) / 2), n - 1] : n ? [0] : []).filter(
    (i, k, all) => k === 0 || (i !== all[k - 1] && x(i) - x(all[k - 1]) >= MIN_TICK_GAP),
  )
  const tooltipLeft = hover != null ? Math.min(x(hover) + 12, width - 190) : 0

  return (
    <div className="space-y-2">
      {series.length > 1 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className="h-0.5 w-3 rounded" style={{ background: s.color }} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <div ref={ref} className="relative w-full">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={ariaLabel}
          className="block touch-none select-none"
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
        >
          {Array.from({ length: GRID_LINES + 1 }).map((_, i) => {
            const v = (top * i) / GRID_LINES
            return (
              <g key={i}>
                <line
                  x1={PAD.left}
                  x2={width - PAD.right}
                  y1={y(v)}
                  y2={y(v)}
                  stroke={i === 0 ? 'var(--color-viz-axis)' : 'var(--color-viz-grid)'}
                  strokeWidth={1}
                />
                <text
                  x={PAD.left - 8}
                  y={y(v)}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-muted-foreground text-[10px] tabular-nums"
                >
                  {formatValue(v)}
                </text>
              </g>
            )
          })}
          {xTicks.map((i, k) => (
            <text
              key={i}
              x={x(i)}
              y={height - 6}
              textAnchor={k === 0 ? 'start' : k === xTicks.length - 1 ? 'end' : 'middle'}
              className="fill-muted-foreground text-[10px] tabular-nums"
            >
              {timeLabel(times[i], span)}
            </text>
          ))}
          {series.length === 1 && n > 1 && (
            <path
              d={`${path(series[0].values)}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`}
              fill={series[0].color}
              fillOpacity={0.1}
            />
          )}
          {series.map((s) => (
            <path
              key={s.key}
              d={path(s.values)}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {hover != null && (
            <g>
              <line
                x1={x(hover)}
                x2={x(hover)}
                y1={PAD.top}
                y2={PAD.top + innerH}
                stroke="var(--color-viz-axis)"
                strokeWidth={1}
              />
              {series.map((s) => (
                <circle
                  key={s.key}
                  cx={x(hover)}
                  cy={y(s.values[hover])}
                  r={4}
                  fill={s.color}
                  stroke="var(--color-card)"
                  strokeWidth={2}
                />
              ))}
            </g>
          )}
        </svg>
        {hover != null && (
          <div
            className="pointer-events-none absolute top-1 z-10 min-w-[170px] rounded-md border bg-popover px-3 py-2 text-xs shadow-md"
            style={{ left: tooltipLeft }}
          >
            <div className="mb-1 text-muted-foreground">{times[hover].toLocaleString()}</div>
            {series.map((s) => (
              <div key={s.key} className="flex items-center gap-2">
                <span className="h-0.5 w-3 rounded" style={{ background: s.color }} aria-hidden />
                <span className="font-semibold tabular-nums">{formatValue(s.values[hover])}</span>
                <span className="text-muted-foreground">{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
