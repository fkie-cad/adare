import { useState } from 'react'
import { useParams, Link } from '@tanstack/react-router'
import { CheckSquare, Server } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { VerifyEnvironmentDialog } from '@/components/dialogs/verify-environment-dialog'
import { useEnvironment } from '@/api/hooks/use-environments'
import { useRuns } from '@/api/hooks/use-runs'
import { formatDateTime, formatDuration } from '@/lib/formatters'

function SyncBadge({ synced }: { synced: unknown }) {
  if (synced === true) return <Badge variant="success">Synced</Badge>
  if (synced === false) return <Badge variant="warning">Unsynced</Badge>
  return <>—</>
}

export default function EnvironmentDetailPage() {
  const { name } = useParams({ from: '/environments/$name' })
  const environmentQuery = useEnvironment(name)
  const runsQuery = useRuns({ environment: name })
  const [verifyOpen, setVerifyOpen] = useState(false)

  const env = environmentQuery.data
  const projectPath = env?.project_path ? String(env.project_path) : ''

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title={name}
        description="Environment details"
        actions={
          <Button onClick={() => setVerifyOpen(true)} disabled={!projectPath}>
            <CheckSquare size={14} />
            Verify
          </Button>
        }
      />

      <AsyncBoundary
        isPending={environmentQuery.isPending}
        isError={environmentQuery.isError}
        error={environmentQuery.error}
        onRetry={() => environmentQuery.refetch()}
        errorFallbackMessage="Failed to load environment."
        loadingFallback={<Skeleton className="h-32 w-full" />}
        emptyIcon={Server}
      >
        {env && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Overview</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">OS</dt>
                  <dd className="text-sm">{(env as { os?: string }).os || '—'}</dd>
                </div>
                <div className="space-y-1">
                  <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Sync</dt>
                  <dd className="text-sm">
                    <SyncBadge synced={(env as { synced?: unknown }).synced} />
                  </dd>
                </div>
                <div className="space-y-1">
                  <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">VM</dt>
                  <dd className="text-sm font-mono break-all">{env.vm || '—'}</dd>
                </div>
                <div className="space-y-1">
                  <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Project</dt>
                  <dd className="text-sm font-mono break-all">{projectPath || '—'}</dd>
                </div>
                {env.recipe && (
                  <div className="space-y-1 sm:col-span-2">
                    <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Recipe</dt>
                    <dd className="text-sm">
                      {env.recipe.profile} · {env.recipe.disk_size ?? '—'} · {env.recipe.ram_mb ?? '—'}MB ·{' '}
                      {env.recipe.cpus ?? '—'} CPUs
                    </dd>
                  </div>
                )}
              </dl>
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
            emptyDescription="Run an experiment against this environment to see results here."
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Experiment</TableHead>
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
                    <TableCell>
                      {(run as { experiment_name?: string }).experiment_name ? (
                        <Link
                          to="/experiments/$name"
                          params={{ name: (run as { experiment_name?: string }).experiment_name! }}
                          className="hover:underline"
                        >
                          {(run as { experiment_name?: string }).experiment_name}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </TableCell>
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

      <VerifyEnvironmentDialog
        open={verifyOpen}
        onOpenChange={setVerifyOpen}
        environmentName={name}
        projectPath={projectPath || null}
      />
    </div>
  )
}
