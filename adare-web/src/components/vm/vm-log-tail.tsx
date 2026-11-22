import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrowDownToLine, Eraser, FileText, Pause, Play, WrapText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchVmInstanceLogChunk, useVmInstanceLogs } from '@/api/hooks/use-vms'
import { cn } from '@/lib/utils'

const POLL_MS = 1000
const ERROR_POLL_MS = 5000
/** Characters kept in the view; older output is dropped from the top. */
const MAX_CHARS = 512 * 1024

/** Order the tabs: the logs people watch most first, the rest alphabetically. */
const PREFERRED = ['run/adare.log', 'run/adarevm.log', 'run/serial_console.log', 'run/session.log']

function sortSources<T extends { key: string }>(sources: T[]): T[] {
  const rank = (key: string) => {
    const i = PREFERRED.indexOf(key)
    return i === -1 ? PREFERRED.length + (key === 'libvirt' ? 1 : 0) : i
  }
  return [...sources].sort((a, b) => rank(a.key) - rank(b.key) || a.key.localeCompare(b.key))
}

function labelFor(key: string, name: string): string {
  return key === 'libvirt' ? 'libvirt (domain)' : name
}

/**
 * Follow one log file of a running instance: polls the backend for what was appended
 * since the last read and appends it, like `tail -f`.
 */
function useLogTail(instanceId: string, sourceKey: string | null, paused: boolean) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const offsetRef = useRef<number | null>(null)

  // A new source starts over from the end of that file.
  useEffect(() => {
    offsetRef.current = null
    setText('')
    setError(null)
    setLoaded(false)
  }, [instanceId, sourceKey])

  useEffect(() => {
    if (!sourceKey || paused) return
    let cancelled = false
    let timer: number | undefined

    const tick = async () => {
      let delay = POLL_MS
      try {
        const chunk = await fetchVmInstanceLogChunk(instanceId, sourceKey, offsetRef.current)
        if (cancelled) return
        offsetRef.current = chunk.next_offset
        setError(null)
        setLoaded(true)
        if (chunk.reset || chunk.text) {
          setText((prev) => {
            const next = (chunk.reset ? '' : prev) + chunk.text
            if (next.length <= MAX_CHARS) return next
            // Drop whole lines from the top.
            const cut = next.indexOf('\n', next.length - MAX_CHARS)
            return cut === -1 ? next.slice(-MAX_CHARS) : next.slice(cut + 1)
          })
        }
      } catch (err) {
        if (cancelled) return
        setError((err as Error)?.message ?? 'Failed to read log')
        setLoaded(true)
        delay = ERROR_POLL_MS
      }
      if (!cancelled) timer = window.setTimeout(tick, delay)
    }
    tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [instanceId, sourceKey, paused])

  const clear = useCallback(() => setText(''), [])
  return { text, error, loaded, clear }
}

interface VmLogTailProps {
  instanceId: string
  className?: string
}

/** Live, read-only log view of a running VM instance, one tab per log file. */
export function VmLogTail({ instanceId, className }: VmLogTailProps) {
  const sourcesQuery = useVmInstanceLogs(instanceId)
  const sources = sortSources(sourcesQuery.data ?? [])
  const [selected, setSelected] = useState<string | null>(null)
  const [paused, setPaused] = useState(false)
  const [follow, setFollow] = useState(true)
  const [wrap, setWrap] = useState(true)
  const [filter, setFilter] = useState('')

  // Keep the chosen log while it exists; otherwise fall back to the first one.
  const active = selected && sources.some((s) => s.key === selected) ? selected : (sources[0]?.key ?? null)
  const { text, error, loaded, clear } = useLogTail(instanceId, active, paused)

  const shown = filter
    ? text
        .split('\n')
        .filter((line) => line.toLowerCase().includes(filter.toLowerCase()))
        .join('\n')
    : text

  const scrollRef = useRef<HTMLPreElement>(null)
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && follow) el.scrollTop = el.scrollHeight
  }, [shown, follow])

  // Scrolling up stops following; scrolling back to the bottom resumes it.
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24
    if (atBottom !== follow) setFollow(atBottom)
  }

  return (
    <div className={cn('flex min-h-0 flex-col', className)}>
      <div className="flex flex-wrap items-center gap-1 border-b border-border px-2 py-1.5">
        {sources.map((s) => (
          <Button
            key={s.key}
            variant={s.key === active ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setSelected(s.key)}
            title={s.key}
          >
            {labelFor(s.key, s.name)}
          </Button>
        ))}
        <div className="ml-auto flex items-center gap-1">
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter lines"
            className="h-8 w-36"
          />
          <Button
            variant="ghost"
            size="icon"
            title={paused ? 'Resume' : 'Pause'}
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? <Play size={14} /> : <Pause size={14} />}
          </Button>
          <Button
            variant={follow ? 'secondary' : 'ghost'}
            size="icon"
            title="Follow the end of the log"
            onClick={() => setFollow((f) => !f)}
          >
            <ArrowDownToLine size={14} />
          </Button>
          <Button
            variant={wrap ? 'secondary' : 'ghost'}
            size="icon"
            title="Wrap long lines"
            onClick={() => setWrap((w) => !w)}
          >
            <WrapText size={14} />
          </Button>
          <Button variant="ghost" size="icon" title="Clear the view" onClick={clear}>
            <Eraser size={14} />
          </Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        {sourcesQuery.isPending ? (
          <div className="space-y-2 p-3">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : sources.length === 0 ? (
          <div className="flex h-full items-center justify-center p-4">
            <EmptyState
              icon={FileText}
              title="No logs yet"
              description={
                sourcesQuery.isError
                  ? (sourcesQuery.error as Error)?.message
                  : 'This instance has no run logs (yet) and no readable libvirt log.'
              }
            />
          </div>
        ) : (
          <pre
            ref={scrollRef}
            onScroll={handleScroll}
            className={cn(
              'absolute inset-0 overflow-auto bg-muted/30 p-3 font-mono text-xs leading-relaxed',
              wrap ? 'whitespace-pre-wrap break-all' : 'whitespace-pre',
            )}
          >
            {!loaded ? 'Loading…' : shown || (filter ? 'No matching lines.' : 'Waiting for output…')}
          </pre>
        )}
        {(error || paused) && sources.length > 0 && (
          <span className="pointer-events-none absolute right-3 top-2 rounded-md bg-background/90 px-2 py-1 text-xs text-muted-foreground">
            {paused ? 'Paused' : `Error: ${error}`}
          </span>
        )}
      </div>
    </div>
  )
}
