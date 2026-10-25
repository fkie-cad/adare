import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Plus, Sparkles, SquareTerminal, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useProjects } from '@/api/hooks/use-projects'
import { useCloseTerminal, useTerminals } from '@/api/hooks/use-terminals'
import { useTerminalStore } from '@/stores/terminal-store'
import { TerminalView } from '@/components/terminal/terminal-view'
import { CWD_KEY, useLaunchTerminal } from '@/components/terminal/use-launch-terminal'

const MIN_HEIGHT = 160

function rememberedCwd(): string {
  try {
    return localStorage.getItem(CWD_KEY) ?? ''
  } catch {
    return ''
  }
}

/**
 * A terminal dock along the bottom of every page: tabs of server-side sessions
 * (Claude Code or a shell, in a chosen project), resizable, toggled with Ctrl+`.
 * Sessions keep running while the panel is hidden or the page reloads.
 */
export function TerminalPanel() {
  const { open, height, activeId, setOpen, toggle, setHeight, setActive } = useTerminalStore()
  const [everOpened, setEverOpened] = useState(open)
  const sessions = useTerminals(everOpened)
  const projects = useProjects()
  const close = useCloseTerminal()
  const { launch, isPending } = useLaunchTerminal()
  const [cwd, setCwd] = useState(rememberedCwd)
  const dragStart = useRef<{ y: number; height: number } | null>(null)

  useEffect(() => {
    if (open) setEverOpened(true)
  }, [open])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === '`') {
        e.preventDefault()
        toggle()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  const list = sessions.data ?? []
  const projectList = projects.data ?? []
  const selectedCwd = cwd || projectList[0]?.path || ''
  const current = list.find((s) => s.id === activeId) ?? list[list.length - 1]

  useEffect(() => {
    if (current && current.id !== activeId) setActive(current.id)
  }, [current, activeId, setActive])

  const chooseCwd = (path: string) => {
    setCwd(path)
    try {
      localStorage.setItem(CWD_KEY, path)
    } catch {
      // storage unavailable: the choice lasts until reload
    }
  }

  const onDragStart = (e: React.PointerEvent) => {
    dragStart.current = { y: e.clientY, height }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onDragMove = (e: React.PointerEvent) => {
    if (!dragStart.current) return
    const next = dragStart.current.height + (dragStart.current.y - e.clientY)
    setHeight(Math.max(MIN_HEIGHT, Math.min(window.innerHeight - 120, next)))
  }

  if (!everOpened) return null

  return (
    <section
      className={cn('relative flex shrink-0 flex-col border-t border-border bg-[#0b1416]', !open && 'hidden')}
      style={{ height }}
      aria-label="Terminals"
    >
      <div
        className="absolute inset-x-0 -top-1 z-10 h-2 cursor-row-resize"
        onPointerDown={onDragStart}
        onPointerMove={onDragMove}
        onPointerUp={() => (dragStart.current = null)}
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize terminal panel"
      />
      <div className="flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-white/10 bg-card px-2">
        {list.map((s) => (
          <div
            key={s.id}
            className={cn(
              'group flex shrink-0 items-center gap-1.5 rounded-md py-1 pl-2.5 pr-1 text-sm',
              s.id === current?.id ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted',
            )}
          >
            <button type="button" className="flex items-center gap-1.5" onClick={() => setActive(s.id)} title={s.cwd}>
              {s.kind === 'claude' ? (
                <Sparkles className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <SquareTerminal className="h-3.5 w-3.5" aria-hidden />
              )}
              <span className={cn('max-w-[220px] truncate', !s.running && 'line-through opacity-70')}>{s.title}</span>
            </button>
            <button
              type="button"
              className="rounded p-0.5 opacity-60 hover:bg-background/40 hover:opacity-100"
              onClick={() => close.mutate(s.id)}
              aria-label={`Close ${s.title}`}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}

        <div className="ml-auto flex shrink-0 items-center gap-1.5 pl-2">
          <select
            value={selectedCwd}
            onChange={(e) => chooseCwd(e.target.value)}
            className="h-7 max-w-[180px] rounded-md border border-input bg-background px-2 text-xs"
            aria-label="Project to start in"
          >
            {projectList.map((p) => (
              <option key={p.path} value={p.path}>
                {p.name}
              </option>
            ))}
            {projectList.length === 0 && <option value="">Home directory</option>}
          </select>
          <Button
            size="sm"
            className="h-7"
            disabled={isPending}
            onClick={() => launch({ kind: 'claude', cwd: selectedCwd || undefined })}
          >
            <Sparkles size={14} />
            Claude
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7"
            disabled={isPending}
            onClick={() => launch({ kind: 'shell', cwd: selectedCwd || undefined })}
          >
            <Plus size={14} />
            Shell
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            onClick={() => setOpen(false)}
            aria-label="Hide terminal panel (Ctrl+`)"
            title="Hide (Ctrl+`)"
          >
            <ChevronDown size={16} />
          </Button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        {list.map((s) => (
          <div key={s.id} className={cn('absolute inset-0', s.id !== current?.id && 'hidden')}>
            <TerminalView sessionId={s.id} active={open && s.id === current?.id} />
          </div>
        ))}
        {list.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-slate-400">
            <Sparkles className="h-6 w-6" aria-hidden />
            <p>
              Start <strong className="text-slate-200">Claude</strong> in a project to create, run and debug experiments
              with the ADARE skills, or open a shell.
            </p>
            <p className="text-xs text-slate-500">Sessions keep running when you hide this panel or reload the page.</p>
          </div>
        )}
      </div>
    </section>
  )
}
