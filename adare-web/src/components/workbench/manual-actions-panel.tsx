import { useEffect, useState } from 'react'
import { parse, stringify } from 'yaml'
import { Play, Plus, ListChecks, Trash2, Loader2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { FormField } from '@/components/ui/form-field'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { toast } from '@/components/ui/toast'
import { useActionTypes, useExecuteAction } from '@/api/hooks/use-actions'
import { useExecutionStore } from '@/stores/execution-store'
import { usePlaybookStore } from '@/stores/playbook-store'
import type {
  Action,
  ActionTypeMetadata,
  Target,
  TargetType,
  StrategyType,
  MouseButton,
  ScrollDirection,
} from '@/types/action'

const selectClass =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'

const STRUCTURED = new Set(['Click', 'Keyboard', 'Wait', 'Scroll', 'Command', 'Screenshot'])
const STRATEGIES: StrategyType[] = [
  'sweep',
  'best_confidence',
  'closest_to',
  'leftmost',
  'rightmost',
  'topmost',
  'bottommost',
]
const CATEGORY_LABELS: Record<string, string> = {
  gui: 'GUI',
  control: 'Control flow',
  data: 'Data',
  system: 'System',
}

type ActionDraft = { type: string; [key: string]: unknown }

interface Props {
  sessionId: string
}

export function ManualActionsPanel({ sessionId }: Props) {
  const { data: actionTypes, isPending, isError, error, refetch } = useActionTypes()
  const executeAction = useExecuteAction(sessionId)
  const setActionTypes = usePlaybookStore((s) => s.setActionTypes)
  const addAction = usePlaybookStore((s) => s.addAction)
  const log = useExecutionStore((s) => s.log)
  const addExecution = useExecutionStore((s) => s.addExecution)
  const updateExecution = useExecutionStore((s) => s.updateExecution)
  const clearLog = useExecutionStore((s) => s.clearLog)

  const [draft, setDraft] = useState<ActionDraft | null>(null)
  const [rawText, setRawText] = useState('')

  useEffect(() => {
    if (actionTypes && actionTypes.length > 0) setActionTypes(actionTypes)
  }, [actionTypes, setActionTypes])

  const selectPaletteItem = (meta: ActionTypeMetadata) => {
    const seed: ActionDraft = { type: meta.type, ...(meta.default_params as object) }
    setDraft(seed)
    setRawText(stringify(seed))
  }

  const structured = !!draft && STRUCTURED.has(draft.type)

  const buildAction = (): Action | null => {
    if (!draft) return null
    if (structured) return draft as unknown as Action
    try {
      return parse(rawText) as Action
    } catch {
      return null
    }
  }

  const serializeYaml = (): string => (structured ? stringify(draft) : rawText)

  const handleExecute = () => {
    if (!draft) return
    const id = addExecution(draft.type, typeof draft.description === 'string' ? draft.description : undefined)
    executeAction.mutate(
      { action_yaml: serializeYaml() },
      {
        onSuccess: (result) => {
          updateExecution(id, result.success ? 'success' : 'error', result)
          if (result.success) toast.success('Action executed', result.message)
          else toast.error('Action failed', result.error_message ?? result.message)
        },
        onError: (err) => {
          updateExecution(id, 'error')
          toast.error('Execution failed', (err as Error)?.message)
        },
      },
    )
  }

  const handleAddToPlaybook = () => {
    const action = buildAction()
    if (!action) {
      toast.error('Invalid action', 'Could not parse the action YAML.')
      return
    }
    addAction(action)
    toast.success('Added to playbook', draft?.type)
  }

  const setField = (key: string, value: unknown) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d))

  const setTargetField = (patch: Partial<Target>) =>
    setDraft((d) => {
      if (!d) return d
      const target = (d.target as Target | undefined) ?? { type: 'image' as TargetType }
      return { ...d, target: { ...target, ...patch } }
    })

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="flex flex-col">
        <CardContent className="pt-6 space-y-4">
          <div>
            <h3 className="text-sm font-semibold mb-2">Action palette</h3>
            <AsyncBoundary
              isPending={isPending}
              isError={isError}
              error={error}
              onRetry={() => refetch()}
              loadingFallback={<p className="text-sm text-muted-foreground">Loading actions…</p>}
              isEmpty={actionTypes?.length === 0}
              emptyIcon={ListChecks}
              emptyTitle="No action types"
              emptyDescription="The backend returned no action metadata."
            >
              <div className="space-y-3">
                {Object.entries(groupByCategory(actionTypes ?? [])).map(([category, items]) => (
                  <div key={category}>
                    <p className="text-xs font-medium text-muted-foreground mb-1.5">
                      {CATEGORY_LABELS[category] ?? category}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {items.map((meta) => (
                        <Button
                          key={meta.type}
                          variant={draft?.type === meta.type ? 'default' : 'outline'}
                          size="sm"
                          title={meta.description}
                          onClick={() => selectPaletteItem(meta)}
                        >
                          {meta.display_name}
                        </Button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </AsyncBoundary>
          </div>

          {draft && (
            <div className="space-y-3 border-t border-border pt-4">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{draft.type}</Badge>
                <span className="text-xs text-muted-foreground">Configure &amp; run</span>
              </div>

              {structured ? (
                <ActionFields draft={draft} setField={setField} setTargetField={setTargetField} />
              ) : (
                <FormField label="Action YAML" htmlFor="raw-action">
                  <Textarea
                    id="raw-action"
                    className="font-mono text-xs min-h-[160px]"
                    value={rawText}
                    onChange={(e) => setRawText(e.target.value)}
                  />
                </FormField>
              )}

              <FormField label="Description" htmlFor="action-desc" hint="Optional">
                <Input
                  id="action-desc"
                  value={typeof draft.description === 'string' ? draft.description : ''}
                  onChange={(e) => setField('description', e.target.value || undefined)}
                  placeholder="Human-readable label"
                />
              </FormField>

              <div className="flex flex-wrap gap-2">
                <Button onClick={handleExecute} disabled={!sessionId || executeAction.isPending}>
                  {executeAction.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Play size={14} />
                  )}
                  Execute
                </Button>
                <Button variant="outline" onClick={handleAddToPlaybook}>
                  <Plus size={14} />
                  Add to playbook
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="flex flex-col max-h-[70vh]">
        <CardContent className="pt-6 flex flex-col flex-1 min-h-0">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Execution log</h3>
            {log.length > 0 && (
              <Button variant="ghost" size="sm" onClick={clearLog}>
                <Trash2 size={14} />
                Clear
              </Button>
            )}
          </div>
          <div className="flex-1 overflow-y-auto space-y-2">
            {log.length === 0 ? (
              <EmptyState
                icon={Play}
                title="Nothing run yet"
                description="Configure an action and execute it."
              />
            ) : (
              log.map((entry) => (
                <div key={entry.id} className="rounded-md border border-border p-3 space-y-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{entry.action_type}</Badge>
                    <Badge variant={statusToVariant(entry.status)} className="ml-auto">
                      {entry.status}
                    </Badge>
                    {entry.duration_ms != null && (
                      <span className="text-xs font-mono text-muted-foreground">
                        {formatMs(entry.duration_ms)}
                      </span>
                    )}
                  </div>
                  {entry.description && <p className="text-sm">{entry.description}</p>}
                  {entry.result?.message && (
                    <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                      {entry.result.message}
                    </p>
                  )}
                  {entry.result?.error_message && (
                    <p className="text-xs text-destructive whitespace-pre-wrap">
                      {entry.result.error_message}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function groupByCategory(items: ActionTypeMetadata[]): Record<string, ActionTypeMetadata[]> {
  return items.reduce<Record<string, ActionTypeMetadata[]>>((acc, item) => {
    ;(acc[item.category] ??= []).push(item)
    return acc
  }, {})
}

function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`
}

interface FieldsProps {
  draft: ActionDraft
  setField: (key: string, value: unknown) => void
  setTargetField: (patch: Partial<Target>) => void
}

function ActionFields({ draft, setField, setTargetField }: FieldsProps) {
  const target = (draft.target as Target | undefined) ?? { type: 'image' }
  const str = (v: unknown) => (typeof v === 'string' ? v : '')
  const num = (v: unknown) => (typeof v === 'number' ? String(v) : '')

  switch (draft.type) {
    case 'Click':
      return (
        <>
          <FormField label="Target type" htmlFor="cl-target-type">
            <select
              id="cl-target-type"
              className={selectClass}
              value={target.type}
              onChange={(e) => setTargetField({ type: e.target.value as TargetType })}
            >
              <option value="image">image</option>
              <option value="text">text</option>
            </select>
          </FormField>
          {target.type === 'image' ? (
            <FormField label="Image path" htmlFor="cl-image">
              <Input
                id="cl-image"
                value={str(target.image)}
                onChange={(e) => setTargetField({ image: e.target.value })}
                placeholder="button.png"
              />
            </FormField>
          ) : (
            <FormField label="Text" htmlFor="cl-text">
              <Input
                id="cl-text"
                value={str(target.text)}
                onChange={(e) => setTargetField({ text: e.target.value })}
                placeholder="OK"
              />
            </FormField>
          )}
          <FormField label="Strategy" htmlFor="cl-strategy">
            <select
              id="cl-strategy"
              className={selectClass}
              value={str(draft.strategy) || 'sweep'}
              onChange={(e) => setField('strategy', e.target.value as StrategyType)}
            >
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Button" htmlFor="cl-button">
              <select
                id="cl-button"
                className={selectClass}
                value={str(draft.button) || 'left'}
                onChange={(e) => setField('button', e.target.value as MouseButton)}
              >
                <option value="left">left</option>
                <option value="right">right</option>
                <option value="middle">middle</option>
              </select>
            </FormField>
            <div className="flex items-end">
              <label className="flex items-center gap-2 pb-2.5 text-sm">
                <Checkbox
                  checked={draft.double_click === true}
                  onChange={(e) => setField('double_click', e.target.checked)}
                />
                Double click
              </label>
            </div>
            <FormField label="Offset X" htmlFor="cl-ox">
              <Input
                id="cl-ox"
                type="number"
                value={num(draft.offset_x)}
                onChange={(e) => setField('offset_x', e.target.value === '' ? undefined : Number(e.target.value))}
              />
            </FormField>
            <FormField label="Offset Y" htmlFor="cl-oy">
              <Input
                id="cl-oy"
                type="number"
                value={num(draft.offset_y)}
                onChange={(e) => setField('offset_y', e.target.value === '' ? undefined : Number(e.target.value))}
              />
            </FormField>
          </div>
        </>
      )

    case 'Keyboard':
      return (
        <>
          <FormField label="Text" htmlFor="kb-text" hint="Type this literal string">
            <Input
              id="kb-text"
              value={str(draft.text)}
              onChange={(e) => setField('text', e.target.value || undefined)}
              placeholder="hello world"
            />
          </FormField>
          <FormField label="Keys" htmlFor="kb-keys" hint="Comma-separated, e.g. ctrl, c">
            <Input
              id="kb-keys"
              value={Array.isArray(draft.keys) ? (draft.keys as string[]).join(', ') : ''}
              onChange={(e) =>
                setField(
                  'keys',
                  e.target.value.trim()
                    ? e.target.value.split(',').map((k) => k.trim()).filter(Boolean)
                    : undefined,
                )
              }
              placeholder="ctrl, c"
            />
          </FormField>
          <FormField label="Wait (s)" htmlFor="kb-wait" hint="Delay after typing">
            <Input
              id="kb-wait"
              type="number"
              step="0.1"
              value={num(draft.wait)}
              onChange={(e) => setField('wait', e.target.value === '' ? undefined : Number(e.target.value))}
            />
          </FormField>
        </>
      )

    case 'Wait':
      return (
        <FormField label="Seconds" htmlFor="wt-seconds">
          <Input
            id="wt-seconds"
            type="number"
            step="0.1"
            value={num(draft.seconds)}
            onChange={(e) => setField('seconds', e.target.value === '' ? undefined : Number(e.target.value))}
          />
        </FormField>
      )

    case 'Scroll':
      return (
        <>
          <FormField label="Direction" htmlFor="sc-dir">
            <select
              id="sc-dir"
              className={selectClass}
              value={str(draft.direction) || 'down'}
              onChange={(e) => setField('direction', e.target.value as ScrollDirection)}
            >
              <option value="up">up</option>
              <option value="down">down</option>
              <option value="left">left</option>
              <option value="right">right</option>
            </select>
          </FormField>
          <FormField label="Amount" htmlFor="sc-amount">
            <Input
              id="sc-amount"
              type="number"
              value={num(draft.amount)}
              onChange={(e) => setField('amount', e.target.value === '' ? undefined : Number(e.target.value))}
            />
          </FormField>
        </>
      )

    case 'Command':
      return (
        <>
          <FormField label="Command" htmlFor="cmd-command" required>
            <Input
              id="cmd-command"
              className="font-mono text-xs"
              value={str(draft.command)}
              onChange={(e) => setField('command', e.target.value)}
              placeholder="ls -la"
            />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-end">
              <label className="flex items-center gap-2 pb-2.5 text-sm">
                <Checkbox
                  checked={draft.wait_for_completion !== false}
                  onChange={(e) => setField('wait_for_completion', e.target.checked)}
                />
                Wait for completion
              </label>
            </div>
            <FormField label="Timeout (s)" htmlFor="cmd-timeout">
              <Input
                id="cmd-timeout"
                type="number"
                value={num(draft.timeout_seconds)}
                onChange={(e) =>
                  setField('timeout_seconds', e.target.value === '' ? undefined : Number(e.target.value))
                }
              />
            </FormField>
          </div>
        </>
      )

    case 'Screenshot':
      return (
        <FormField label="Filename" htmlFor="ss-filename" required>
          <Input
            id="ss-filename"
            value={str(draft.filename)}
            onChange={(e) => setField('filename', e.target.value)}
            placeholder="screen.png"
          />
        </FormField>
      )

    default:
      return null
  }
}
