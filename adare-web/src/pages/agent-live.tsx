import { useEffect, useReducer, useRef, useState } from 'react'
import { Bot, Play, Loader2, Image as ImageIcon } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { useSessions } from '@/api/hooks/use-sessions'
import { useRunAgent } from '@/api/hooks/use-gui-agent'
import { endpoints } from '@/api/endpoints'
import { wsManager } from '@/services/websocket'
import type {
  WebSocketMessage,
  AgentStepMessage,
  AgentStatusMessage,
} from '@/types/api'

// One row in the step log. Fields are populated by the `decided` phase and the
// status (plus screenshot) is refined by the matching `executed` phase.
interface StepEntry {
  index: number
  kind: string
  describe: string
  reasoning: string
  coords: [number, number] | null
  grounded: boolean
  status: string
  hasScreenshot: boolean
}

interface AgentState {
  steps: StepEntry[]
  latestImageIndex: number | null
  runState: 'idle' | 'running' | 'finished' | 'failed'
  summary: string | null
}

type AgentAction =
  | { type: 'reset' }
  | { type: 'step'; data: AgentStepMessage['data'] }
  | { type: 'status'; data: AgentStatusMessage['data'] }

const initialState: AgentState = {
  steps: [],
  latestImageIndex: null,
  runState: 'idle',
  summary: null,
}

function agentReducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case 'reset':
      return { ...initialState, runState: 'running' }

    case 'step': {
      const d = action.data
      // pause/resume bracket an interactive gate; web runs are non-interactive
      // so there is nothing to merge into the step log.
      if (d.phase === 'pause' || d.phase === 'resume') return state

      const existing = state.steps.find((s) => s.index === d.index)
      const merged: StepEntry = {
        index: d.index,
        kind: d.kind || existing?.kind || '',
        describe: d.describe || existing?.describe || '',
        reasoning: d.reasoning || existing?.reasoning || '',
        coords: d.coords ?? existing?.coords ?? null,
        grounded: d.grounded ?? existing?.grounded ?? false,
        status: d.status || existing?.status || 'running',
        hasScreenshot: existing?.hasScreenshot || !!d.screenshot,
      }

      const steps = existing
        ? state.steps.map((s) => (s.index === d.index ? merged : s))
        : [...state.steps, merged].sort((a, b) => a.index - b.index)

      const latestImageIndex = d.screenshot
        ? Math.max(state.latestImageIndex ?? 0, d.index)
        : state.latestImageIndex

      return { ...state, steps, latestImageIndex }
    }

    case 'status':
      return { ...state, runState: action.data.state, summary: action.data.summary }

    default:
      return state
  }
}

export default function AgentLivePage() {
  const { data: sessions, isPending: sessionsPending } = useSessions()

  const [sessionId, setSessionId] = useState('')
  const [goal, setGoal] = useState('')
  const [maxSteps, setMaxSteps] = useState('')
  const [planning, setPlanning] = useState(true)
  const [grounding, setGrounding] = useState(true)
  const [video, setVideo] = useState(false)

  const [state, dispatch] = useReducer(agentReducer, initialState)
  const runAgent = useRunAgent(sessionId)
  const logEndRef = useRef<HTMLDivElement>(null)

  // Subscribe to the session's WebSocket for agent frames.
  useEffect(() => {
    if (!sessionId) return

    const client = wsManager.getClient(sessionId)
    const onStep = (msg: WebSocketMessage) =>
      dispatch({ type: 'step', data: (msg as AgentStepMessage).data })
    const onStatus = (msg: WebSocketMessage) =>
      dispatch({ type: 'status', data: (msg as AgentStatusMessage).data })

    client.on('agent_step', onStep)
    client.on('agent_status', onStatus)
    client.connect()

    return () => {
      client.off('agent_step', onStep)
      client.off('agent_status', onStatus)
    }
  }, [sessionId])

  // Keep the newest step visible.
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [state.steps])

  const handleRun = () => {
    if (!sessionId || !goal.trim()) return
    dispatch({ type: 'reset' })
    const parsedMax = parseInt(maxSteps, 10)
    runAgent.mutate({
      goal: goal.trim(),
      max_steps: Number.isFinite(parsedMax) && parsedMax > 0 ? parsedMax : undefined,
      planning,
      grounding,
      video,
    })
  }

  const canRun = !!sessionId && !!goal.trim() && state.runState !== 'running'

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Agent Live" description="Watch the GUI agent work step by step" />

      {/* Controls */}
      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="agent-session">Session</Label>
              <select
                id="agent-session"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">
                  {sessionsPending ? 'Loading sessions…' : 'Select a session…'}
                </option>
                {sessions?.map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    {s.experiment} · {s.environment} ({s.session_id.slice(0, 8)})
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="agent-max-steps">Max steps (optional)</Label>
              <Input
                id="agent-max-steps"
                type="number"
                min={1}
                placeholder="Default"
                value={maxSteps}
                onChange={(e) => setMaxSteps(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="agent-goal">Goal</Label>
            <Textarea
              id="agent-goal"
              placeholder="Describe what the agent should accomplish…"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={planning} onChange={(e) => setPlanning(e.target.checked)} />
              Planning
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={grounding} onChange={(e) => setGrounding(e.target.checked)} />
              Grounding
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={video} onChange={(e) => setVideo(e.target.checked)} />
              Video
            </label>

            <Button className="ml-auto" onClick={handleRun} disabled={!canRun}>
              {state.runState === 'running' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              Run agent
            </Button>
          </div>

          {runAgent.isError && (
            <p className="text-sm text-destructive">
              {(runAgent.error as Error)?.message ?? 'Failed to start agent.'}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Run summary */}
      {(state.runState === 'finished' || state.runState === 'failed') && state.summary && (
        <Card
          className={cn(state.runState === 'failed' && 'border-destructive')}
        >
          <CardContent className="pt-6 flex items-start gap-3">
            <Badge variant={statusToVariant(state.runState)}>{state.runState}</Badge>
            <p className="text-sm flex-1 whitespace-pre-wrap">{state.summary}</p>
          </CardContent>
        </Card>
      )}

      {/* Two-pane layout: step log + latest screenshot */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Step log */}
        <Card className="flex flex-col max-h-[70vh]">
          <CardContent className="pt-6 flex-1 overflow-y-auto space-y-3">
            {state.steps.length === 0 ? (
              <EmptyState
                icon={Bot}
                title="No steps yet"
                description="Select a session, set a goal, and run the agent."
              />
            ) : (
              <>
                {state.steps.map((step) => (
                  <div
                    key={step.index}
                    className="rounded-md border border-border p-3 space-y-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-muted-foreground">
                        #{step.index}
                      </span>
                      <Badge variant="secondary">{step.kind || '—'}</Badge>
                      {step.grounded && <Badge variant="outline">grounded</Badge>}
                      <Badge variant={statusToVariant(step.status)} className="ml-auto">
                        {step.status}
                      </Badge>
                    </div>
                    {step.describe && (
                      <p className="text-sm font-medium">{step.describe}</p>
                    )}
                    {step.reasoning && (
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                        {step.reasoning}
                      </p>
                    )}
                    {step.coords && (
                      <p className="text-xs font-mono text-muted-foreground">
                        ({step.coords[0]}, {step.coords[1]})
                      </p>
                    )}
                  </div>
                ))}
                <div ref={logEndRef} />
              </>
            )}
          </CardContent>
        </Card>

        {/* Latest annotated screenshot */}
        <Card className="flex flex-col max-h-[70vh]">
          <CardContent className="pt-6 flex-1 overflow-auto flex items-center justify-center">
            {sessionId && state.latestImageIndex != null ? (
              <img
                key={state.latestImageIndex}
                src={endpoints.agentStepImage(sessionId, state.latestImageIndex)}
                alt={`Annotated screenshot for step ${state.latestImageIndex}`}
                className="max-w-full h-auto rounded-md border border-border"
              />
            ) : (
              <EmptyState
                icon={ImageIcon}
                title="No screenshot yet"
                description="Annotated screenshots appear here as steps execute."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
