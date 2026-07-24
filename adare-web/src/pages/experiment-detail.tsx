import { useState } from 'react'
import { useParams, useNavigate, Link } from '@tanstack/react-router'
import { Bot, FlaskConical, Play } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Spinner } from '@/components/ui/spinner'
import { useExperiment, useRunExperiment } from '@/api/hooks/use-experiments'
import { useRuns } from '@/api/hooks/use-runs'
import { formatDateTime, formatDuration } from '@/lib/formatters'
import { toast } from '@/components/ui/toast'

function projectPathOf(exp: { project_path?: string; project?: string } | undefined): string {
  return String(exp?.project_path ?? exp?.project ?? '')
}

function RunExperimentDialog({
  open,
  onOpenChange,
  name,
  projectPath,
  environments,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  name: string
  projectPath: string
  environments: string[]
}) {
  const [environmentName, setEnvironmentName] = useState(environments[0] ?? '')
  const mutation = useRunExperiment()
  const navigate = useNavigate()

  const handleRun = () => {
    if (!environmentName) return
    mutation.mutate(
      { name, request: { project_path: projectPath, environment_name: environmentName } },
      {
        onSuccess: (data) => {
          onOpenChange(false)
          toast.success('Run started', data.experiment_name)
          navigate({ to: '/runs', search: { focus: data.run_ulid } })
        },
        onError: (err) => toast.error('Failed to start run', (err as Error)?.message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <div className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Run {name}</DialogTitle>
            <DialogDescription>Choose an environment to run this experiment against.</DialogDescription>
          </DialogHeader>

          <FormField label="Environment" htmlFor="run-env" required>
            <select
              id="run-env"
              value={environmentName}
              onChange={(e) => setEnvironmentName(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option value="">Select an environment…</option>
              {environments.map((env) => (
                <option key={env} value={env}>
                  {env}
                </option>
              ))}
            </select>
          </FormField>

          {mutation.isError && (
            <div className="rounded-md border border-destructive bg-destructive/10 p-2 text-xs text-destructive">
              {(mutation.error as Error)?.message ?? 'Failed to start run.'}
            </div>
          )}

          <DialogFooter className="gap-2 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button onClick={handleRun} disabled={!environmentName || mutation.isPending}>
              {mutation.isPending && <Spinner className="h-4 w-4" />}
              Run
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function ExperimentDetailPage() {
  const { name } = useParams({ from: '/experiments/$name' })
  const experimentQuery = useExperiment(name)
  const runsQuery = useRuns({ experiment: name })
  const [runOpen, setRunOpen] = useState(false)

  const exp = experimentQuery.data
  const envNames: string[] = exp?.environment_names ?? []
  const tags: string[] = Array.isArray(exp?.tags) ? exp.tags : []
  const projectPath = projectPathOf(exp)

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title={name}
        description="Experiment details"
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/develop" search={{ experiment: name, environment: envNames[0] }}>
                <Bot size={14} />
                Develop
              </Link>
            </Button>
            <Button onClick={() => setRunOpen(true)} disabled={envNames.length === 0}>
              <Play size={14} />
              Run
            </Button>
          </>
        }
      />

      <AsyncBoundary
        isPending={experimentQuery.isPending}
        isError={experimentQuery.isError}
        error={experimentQuery.error}
        onRetry={() => experimentQuery.refetch()}
        errorFallbackMessage="Failed to load experiment."
        loadingFallback={<Skeleton className="h-32 w-full" />}
        emptyIcon={FlaskConical}
      >
        {exp && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Project</p>
                  <p className="text-sm font-mono">{projectPath || '—'}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Tags</p>
                  <div className="flex flex-wrap gap-1">
                    {tags.length > 0 ? (
                      tags.map((tag) => (
                        <Badge key={tag} variant="outline">
                          {tag}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-sm">—</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Environments</p>
                <div className="flex flex-wrap gap-1">
                  {envNames.length > 0 ? (
                    envNames.map((env) => (
                      <Link key={env} to="/environments/$name" params={{ name: env }}>
                        <Badge variant="outline" className="hover:bg-accent">
                          {env}
                        </Badge>
                      </Link>
                    ))
                  ) : (
                    <span className="text-sm">No linked environments</span>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </AsyncBoundary>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run history</CardTitle>
        </CardHeader>
        <CardContent>
          <AsyncBoundary
            isPending={runsQuery.isPending}
            isError={runsQuery.isError}
            error={runsQuery.error}
            onRetry={() => runsQuery.refetch()}
            errorFallbackMessage="Failed to load runs."
            loadingFallback={<Skeleton className="h-24 w-full" />}
            isEmpty={runsQuery.data?.length === 0}
            emptyTitle="No runs yet"
            emptyDescription="Run this experiment to see results here."
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Environment</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(runsQuery.data ?? []).map((run) => (
                  <TableRow key={String(run.ulid)} className="hover:bg-muted/50">
                    <TableCell>
                      <Link to="/runs/$ulid" params={{ ulid: String(run.ulid) }} className="inline-flex">
                        <Badge variant={statusToVariant((run as { status?: string }).status ?? null)}>
                          {(run as { status?: string }).status ?? '—'}
                        </Badge>
                      </Link>
                    </TableCell>
                    <TableCell>{(run as { environment_name?: string }).environment_name || '—'}</TableCell>
                    <TableCell>{formatDateTime((run as { start_time?: string }).start_time)}</TableCell>
                    <TableCell>{formatDuration((run as { duration_seconds?: number }).duration_seconds)}</TableCell>
                    <TableCell>{(run as { overall_result?: string }).overall_result || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </AsyncBoundary>
        </CardContent>
      </Card>

      <RunExperimentDialog
        open={runOpen}
        onOpenChange={setRunOpen}
        name={name}
        projectPath={projectPath}
        environments={envNames}
      />
    </div>
  )
}
