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
import {
  TARGET_STRATEGIES,
  makeAction,
  pruneParams,
  type Action,
  type ActionParams,
  type ActionTypeMetadata,
  type ClickType,
  type ScrollDirection,
  type Target,
  type TargetStrategyName,
} from '@/types/action'

const selectClass =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'

// Actions with a dedicated form (parser keys); every other palette entry is edited as YAML.
const STRUCTURED = new Set(['click', 'keyboard', 'idle', 'scroll', 'command', 'screenshot'])
const CATEGORY_LABELS: Record<string, string> = {
  gui: 'GUI',
  control: 'Control flow',
  data: 'Data',
  system: 'System',
}

// `key` is the parser's action key; `params` its mapping (what ends up under `{key: ...}`).
type ActionDraft = { key: string; params: ActionParams }

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
    const params = structuredClone(meta.default_params)
    setDraft({ key: meta.type, params })
    setRawText(stringify(makeAction(meta.type, params)))
  }

  const structured = !!draft && STRUCTURED.has(draft.key)

  // The action exactly as the parser accepts it: `{<key>: {params}}`.
  const buildAction = (): Action | null => {
    if (!draft) return null
    if (structured) return makeAction(draft.key, pruneParams(draft.params))
    try {
      const parsed = parse(rawText)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Action) : null
    } catch {
      return null
    }
  }

  const serializeYaml = (): string | null => {
    const action = buildAction()
    return action ? stringify(action) : null
  }

  const handleExecute = () => {
    if (!draft) return
    const actionYaml = serializeYaml()
    if (!actionYaml) {
      toast.error('Invalid action', 'Could not parse the action YAML.')
      return
    }
    const id = addExecution(draft.key, typeof draft.params.description === 'string' ? draft.params.description : undefined)
    executeAction.mutate(
      { action_yaml: actionYaml },
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
    toast.success('Added to playbook', draft?.key)
  }

  const setField = (key: string, value: unknown) =>
    setDraft((d) => (d ? { ...d, params: { ...d.params, [key]: value } } : d))

  const setTargetField = (patch: Partial<Target> & Record<string, unknown>) =>
    setDraft((d) => {
      if (!d) return d
      const target = (d.params.target as Target | undefined) ?? {}
      return { ...d, params: { ...d.params, target: { ...target, ...patch } } }
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
                          variant={draft?.key === meta.type ? 'default' : 'outline'}
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
                <Badge variant="secondary">{draft.key}</Badge>
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

              {structured && (
                <FormField label="Description" htmlFor="action-desc" hint="Optional">
                  <Input
                    id="action-desc"
                    value={typeof draft.params.description === 'string' ? draft.params.description : ''}
                    onChange={(e) => setField('description', e.target.value || undefined)}
                    placeholder="Human-readable label"
                  />
                </FormField>
              )}

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
  setTargetField: (patch: Partial<Target> & Record<string, unknown>) => void
}

const numOrUndefined = (v: string) => (v === '' ? undefined : Number(v))

function strategyValue(name: string): Record<string, unknown> {
  return { [name]: name === 'SweepStrategy' ? { index: 1 } : {} }
}

function ActionFields({ draft, setField, setTargetField }: FieldsProps) {
  const params = draft.params
  const target = (params.target as (Target & { strategy?: Record<string, unknown> }) | undefined) ?? {}
  const targetKind: 'text' | 'image' = target.image !== undefined && target.text === undefined ? 'image' : 'text'
  const str = (v: unknown) => (typeof v === 'string' ? v : '')
  const num = (v: unknown) => (typeof v === 'number' ? String(v) : '')
  const strategyName = (Object.keys(target.strategy ?? {})[0] as TargetStrategyName | undefined) ?? ''

  switch (draft.key) {
    case 'click':
      return (
        <>
          <FormField label="Target type" htmlFor="cl-target-type">
            <select
              id="cl-target-type"
              className={selectClass}
              value={targetKind}
              onChange={(e) =>
                e.target.value === 'image'
                  ? setTargetField({ image: str(target.image), text: undefined })
                  : setTargetField({ text: str(target.text), image: undefined })
              }
            >
              <option value="text">text</option>
              <option value="image">image</option>
            </select>
          </FormField>
          {targetKind === 'image' ? (
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
          <FormField label="Strategy" htmlFor="cl-strategy" hint="Which match to pick when several are found">
            <select
              id="cl-strategy"
              className={selectClass}
              value={strategyName}
              onChange={(e) =>
                setTargetField({ strategy: e.target.value ? strategyValue(e.target.value) : undefined })
              }
            >
              <option value="">default</option>
              {TARGET_STRATEGIES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/Strategy$/, '')}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Click type" htmlFor="cl-type">
            <select
              id="cl-type"
              className={selectClass}
              value={str(params.type) || 'left'}
              onChange={(e) => setField('type', e.target.value as ClickType)}
            >
              <option value="left">left</option>
              <option value="right">right</option>
              <option value="double">double</option>
            </select>
          </FormField>
        </>
      )

    case 'keyboard':
      return (
        <>
          <FormField label="Text" htmlFor="kb-text" hint="Type this literal string">
            <Input
              id="kb-text"
              value={str(params.text)}
              onChange={(e) => setField('text', e.target.value || undefined)}
              placeholder="hello world"
            />
          </FormField>
          <FormField label="Key" htmlFor="kb-key" hint="Single key press, e.g. enter">
            <Input
              id="kb-key"
              value={str(params.key)}
              onChange={(e) => setField('key', e.target.value || undefined)}
              placeholder="enter"
            />
          </FormField>
          <FormField label="Combination" htmlFor="kb-combo" hint="Comma-separated, e.g. ctrl, c">
            <Input
              id="kb-combo"
              value={Array.isArray(params.combination) ? (params.combination as string[]).join(', ') : ''}
              onChange={(e) =>
                setField(
                  'combination',
                  e.target.value.trim()
                    ? e.target.value.split(',').map((k) => k.trim()).filter(Boolean)
                    : undefined,
                )
              }
              placeholder="ctrl, c"
            />
          </FormField>
        </>
      )

    case 'idle':
      return (
        <FormField label="Duration (s)" htmlFor="id-duration" required>
          <Input
            id="id-duration"
            type="number"
            step="0.1"
            value={num(params.duration)}
            onChange={(e) => setField('duration', numOrUndefined(e.target.value))}
          />
        </FormField>
      )

    case 'scroll':
      return (
        <>
          <FormField label="Direction" htmlFor="sc-dir" required>
            <select
              id="sc-dir"
              className={selectClass}
              value={str(params.direction) || 'down'}
              onChange={(e) => setField('direction', e.target.value as ScrollDirection)}
            >
              <option value="up">up</option>
              <option value="down">down</option>
              <option value="left">left</option>
              <option value="right">right</option>
            </select>
          </FormField>
          <FormField label="Amount" htmlFor="sc-amount" required>
            <Input
              id="sc-amount"
              type="number"
              value={num(params.amount)}
              onChange={(e) => setField('amount', numOrUndefined(e.target.value))}
            />
          </FormField>
        </>
      )

    case 'command':
      return (
        <>
          <FormField label="Command" htmlFor="cmd-command" required>
            <Input
              id="cmd-command"
              className="font-mono text-xs"
              value={str(params.command)}
              onChange={(e) => setField('command', e.target.value)}
              placeholder="ls -la"
            />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-end">
              <label className="flex items-center gap-2 pb-2.5 text-sm">
                <Checkbox
                  checked={params.background === true}
                  onChange={(e) => setField('background', e.target.checked || undefined)}
                />
                Run in background
              </label>
            </div>
            <FormField label="Timeout (s)" htmlFor="cmd-timeout">
              <Input
                id="cmd-timeout"
                type="number"
                value={num(params.timeout)}
                onChange={(e) => setField('timeout', numOrUndefined(e.target.value))}
              />
            </FormField>
          </div>
        </>
      )

    case 'screenshot':
      return (
        <FormField label="Name" htmlFor="ss-name" hint="Optional file name">
          <Input
            id="ss-name"
            value={str(params.name)}
            onChange={(e) => setField('name', e.target.value || undefined)}
            placeholder="screen.png"
          />
        </FormField>
      )

    default:
      return null
  }
}
