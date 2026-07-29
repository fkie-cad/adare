import { useState } from 'react'
import {
  BookOpen,
  ArrowUp,
  ArrowDown,
  Trash2,
  Save,
  FolderOpen,
  FlaskConical,
  Loader2,
  Plus,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { FormField } from '@/components/ui/form-field'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { toast } from '@/components/ui/toast'
import { CreateExperimentDialog } from '@/components/dialogs/create-experiment-dialog'
import { stringify } from 'yaml'
import { usePlaybookStore } from '@/stores/playbook-store'
import { useSavePlaybook, useLoadPlaybook } from '@/api/hooks/use-playbook'
import type { Action } from '@/types/action'
import type { Experiment } from '@/api/hooks/use-experiments'

function actionLabel(action: Action, index: number): string {
  const desc = 'description' in action && action.description ? action.description : undefined
  return desc ? `${action.type} — ${desc}` : `${action.type} #${index + 1}`
}

export function PlaybookPanel() {
  const actions = usePlaybookStore((s) => s.actions)
  const removeAction = usePlaybookStore((s) => s.removeAction)
  const reorderActions = usePlaybookStore((s) => s.reorderActions)
  const selectAction = usePlaybookStore((s) => s.selectAction)
  const selectedActionIndex = usePlaybookStore((s) => s.selectedActionIndex)
  const variables = usePlaybookStore((s) => s.variables)
  const setVariable = usePlaybookStore((s) => s.setVariable)
  const removeVariable = usePlaybookStore((s) => s.removeVariable)
  const exportToYAML = usePlaybookStore((s) => s.exportToYAML)
  const playbookName = usePlaybookStore((s) => s.playbookName)
  const setPlaybookName = usePlaybookStore((s) => s.setPlaybookName)
  const isDirty = usePlaybookStore((s) => s.isDirty)
  const markClean = usePlaybookStore((s) => s.markClean)
  const clearPlaybook = usePlaybookStore((s) => s.clearPlaybook)

  const savePlaybook = useSavePlaybook()

  const [saveName, setSaveName] = useState('')
  const [varKey, setVarKey] = useState('')
  const [varValue, setVarValue] = useState('')
  const [loadName, setLoadName] = useState('')
  const [activeLoad, setActiveLoad] = useState('')
  const [createExpOpen, setCreateExpOpen] = useState(false)

  const loadQuery = useLoadPlaybook(activeLoad)

  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= actions.length) return
    const next = [...actions]
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    reorderActions(next)
  }

  const effectiveName = (saveName.trim() || playbookName).trim()

  const handleSave = () => {
    if (actions.length === 0) return
    // `settings` is a distinct execution-config concept (idle/timeout) the
    // playbook file format expects — not the same as these template `variables`,
    // so it's sent empty rather than repurposed and risking corrupting it for
    // CLI-side playbook loading.
    savePlaybook.mutate(
      { filename: effectiveName, actions, settings: {} },
      {
        onSuccess: () => {
          setPlaybookName(effectiveName)
          markClean()
          toast.success('Playbook saved', effectiveName)
        },
        onError: (err) => toast.error('Failed to save playbook', (err as Error)?.message),
      },
    )
  }

  const handleAddVariable = (e: React.FormEvent) => {
    e.preventDefault()
    if (!varKey.trim()) return
    setVariable(varKey.trim(), varValue)
    setVarKey('')
    setVarValue('')
  }

  const handleExperimentCreated = (experiment: Experiment) => {
    savePlaybook.mutate(
      { filename: experiment.name, actions, settings: {} },
      {
        onSuccess: () => {
          setPlaybookName(experiment.name)
          markClean()
          toast.success('Playbook saved to experiment', experiment.name)
        },
        onError: (err) =>
          toast.error('Experiment created, but playbook save failed', (err as Error)?.message),
      },
    )
  }

  const yamlPreview = exportToYAML()

  return (
    <Card>
      <CardContent className="pt-6 space-y-4">
        <div className="flex items-center gap-2">
          <BookOpen size={16} />
          <h3 className="text-sm font-semibold">Playbook</h3>
          {isDirty && (
            <Badge variant="warning" className="ml-auto">
              unsaved
            </Badge>
          )}
        </div>

        <FormField label="Name" htmlFor="pb-name">
          <Input
            id="pb-name"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            placeholder={playbookName}
          />
        </FormField>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-xs font-medium text-muted-foreground">
              Actions ({actions.length})
            </p>
            {actions.length > 0 && (
              <Button variant="ghost" size="sm" onClick={clearPlaybook}>
                <Trash2 size={14} />
                Clear
              </Button>
            )}
          </div>
          {actions.length === 0 ? (
            <EmptyState
              icon={BookOpen}
              title="Empty playbook"
              description="Add actions from the Manual actions tab."
            />
          ) : (
            <div className="space-y-1.5">
              {actions.map((action, index) => (
                <div
                  key={index}
                  className={`flex items-center gap-1.5 rounded-md border p-2 text-sm ${
                    selectedActionIndex === index ? 'border-primary bg-primary/5' : 'border-border'
                  }`}
                  onClick={() => selectAction(index)}
                >
                  <span className="text-xs font-mono text-muted-foreground">{index + 1}</span>
                  <span className="flex-1 truncate">{actionLabel(action, index)}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    title="Move up"
                    disabled={index === 0}
                    onClick={(e) => {
                      e.stopPropagation()
                      move(index, -1)
                    }}
                  >
                    <ArrowUp size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    title="Move down"
                    disabled={index === actions.length - 1}
                    onClick={(e) => {
                      e.stopPropagation()
                      move(index, 1)
                    }}
                  >
                    <ArrowDown size={14} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    title="Remove"
                    onClick={(e) => {
                      e.stopPropagation()
                      removeAction(index)
                    }}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1.5">Variables</p>
          <div className="space-y-1.5">
            {Object.entries(variables).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2 text-sm">
                <span className="font-mono">{key}</span>
                <span className="text-muted-foreground truncate flex-1">{String(value)}</span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  title="Remove variable"
                  onClick={() => removeVariable(key)}
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            ))}
          </div>
          <form onSubmit={handleAddVariable} className="mt-2 flex items-center gap-2">
            <Input
              value={varKey}
              onChange={(e) => setVarKey(e.target.value)}
              placeholder="key"
              className="h-9"
            />
            <Input
              value={varValue}
              onChange={(e) => setVarValue(e.target.value)}
              placeholder="value"
              className="h-9"
            />
            <Button type="submit" variant="outline" size="sm" disabled={!varKey.trim()}>
              <Plus size={14} />
            </Button>
          </form>
        </div>

        <FormField label="YAML preview" htmlFor="pb-yaml">
          <Textarea
            id="pb-yaml"
            readOnly
            className="font-mono text-xs min-h-[140px]"
            value={yamlPreview}
          />
        </FormField>

        <div className="flex flex-wrap gap-2">
          <Button onClick={handleSave} disabled={actions.length === 0 || savePlaybook.isPending}>
            {savePlaybook.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            Save playbook
          </Button>
          <Button
            variant="outline"
            disabled={actions.length === 0}
            onClick={() => setCreateExpOpen(true)}
          >
            <FlaskConical size={14} />
            Save as new experiment
          </Button>
        </div>

        <div className="border-t border-border pt-4 space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Load playbook</p>
          <div className="flex items-center gap-2">
            <Input
              value={loadName}
              onChange={(e) => setLoadName(e.target.value)}
              placeholder="playbook name"
              className="h-9"
            />
            <Button
              variant="outline"
              size="sm"
              disabled={!loadName.trim() || loadQuery.isFetching}
              onClick={() => setActiveLoad(loadName.trim())}
            >
              {loadQuery.isFetching && activeLoad ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <FolderOpen size={14} />
              )}
              Load
            </Button>
          </div>
          {activeLoad && loadQuery.isError && (
            <p className="text-xs text-destructive">
              {(loadQuery.error as Error)?.message ?? 'Failed to load playbook.'}
            </p>
          )}
          {activeLoad && loadQuery.data && (
            <FormField label={`Loaded: ${activeLoad}`} htmlFor="pb-loaded">
              <Textarea
                id="pb-loaded"
                readOnly
                className="font-mono text-xs min-h-[120px]"
                value={stringify(loadQuery.data)}
              />
            </FormField>
          )}
        </div>
      </CardContent>

      <CreateExperimentDialog
        open={createExpOpen}
        onOpenChange={setCreateExpOpen}
        onCreated={handleExperimentCreated}
      />
    </Card>
  )
}
