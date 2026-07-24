import type { ReactNode } from 'react'
import { useParams, Link } from '@tanstack/react-router'
import { Download, FileText, Play } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Card, CardContent } from '@/components/ui/card'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { useRun, useRunArtifacts, type RunArtifact } from '@/api/hooks/use-runs'
import { endpoints } from '@/api/endpoints'
import { formatDateTime, formatDuration } from '@/lib/formatters'

interface RunDetailShape {
  ulid: string
  experiment_name?: string
  environment_name?: string
  project_name?: string
  start_time?: string
  end_time?: string
  duration_seconds?: number
  status?: string
  result_status?: string
  overall_result?: string
  published?: boolean
  os_info?: string
  vm_box?: string
  test_results?: Array<Record<string, unknown>>
}

function OverviewTab({ run }: { run: RunDetailShape }) {
  const rows: [string, ReactNode][] = [
    ['Status', <Badge variant={statusToVariant(run.status ?? null)}>{run.status ?? '—'}</Badge>],
    ['Result', run.result_status || run.overall_result || '—'],
    [
      'Experiment',
      run.experiment_name ? (
        <Link to="/experiments/$name" params={{ name: run.experiment_name }} className="hover:underline">
          {run.experiment_name}
        </Link>
      ) : (
        '—'
      ),
    ],
    [
      'Environment',
      run.environment_name ? (
        <Link to="/environments/$name" params={{ name: run.environment_name }} className="hover:underline">
          {run.environment_name}
        </Link>
      ) : (
        '—'
      ),
    ],
    ['Project', run.project_name || '—'],
    ['Started', formatDateTime(run.start_time)],
    ['Ended', formatDateTime(run.end_time)],
    ['Duration', formatDuration(run.duration_seconds)],
    ['Published', <Badge variant={run.published ? 'success' : 'outline'}>{run.published ? 'Yes' : 'No'}</Badge>],
    ['OS', run.os_info || '—'],
    ['VM box', run.vm_box || '—'],
  ]

  return (
    <Card>
      <CardContent className="pt-6">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {rows.map(([label, value]) => (
            <div key={label} className="space-y-1">
              <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</dt>
              <dd className="text-sm">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

function TestResultsTab({ results }: { results: Array<Record<string, unknown>> }) {
  if (results.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No test results"
        description="This run has no recorded test results."
      />
    )
  }
  return (
    <div className="space-y-2">
      {results.map((result, i) => (
        <Card key={i}>
          <CardContent className="pt-6">
            <pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(result, null, 2)}</pre>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function ArtifactsTab({ ulid, artifacts }: { ulid: string; artifacts: RunArtifact[] }) {
  const screenshots = artifacts.filter((a) => a.kind === 'screenshot')
  const videos = artifacts.filter((a) => a.kind === 'video')
  const reports = artifacts.filter((a) => a.kind === 'report')
  const others = artifacts.filter((a) => a.kind === 'other')

  if (artifacts.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No artifacts"
        description="Screenshots, video, and reports appear here once the run has produced them."
      />
    )
  }

  return (
    <div className="space-y-6">
      {videos.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Video</h3>
          {videos.map((v) => (
            <video key={v.path} controls className="w-full max-w-2xl rounded-md border border-border">
              <source src={endpoints.runArtifact(ulid, v.path)} />
            </video>
          ))}
        </div>
      )}

      {screenshots.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Screenshots ({screenshots.length})</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {screenshots.map((s) => (
              <a key={s.path} href={endpoints.runArtifact(ulid, s.path)} target="_blank" rel="noreferrer">
                <img
                  src={endpoints.runArtifact(ulid, s.path)}
                  alt={s.path}
                  className="w-full h-auto rounded-md border border-border hover:opacity-80"
                />
              </a>
            ))}
          </div>
        </div>
      )}

      {(reports.length > 0 || others.length > 0) && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Files</h3>
          <ul className="space-y-1">
            {[...reports, ...others].map((f) => (
              <li key={f.path} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
                <span className="font-mono text-xs break-all">{f.path}</span>
                <a
                  href={endpoints.runArtifact(ulid, f.path)}
                  download
                  className="text-muted-foreground hover:text-foreground"
                  title="Download"
                >
                  <Download size={14} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function LogsTab({ ulid, artifacts }: { ulid: string; artifacts: RunArtifact[] }) {
  const logs = artifacts.filter((a) => a.kind === 'log')
  if (logs.length === 0) {
    return <EmptyState icon={FileText} title="No logs" description="No log files were recorded for this run." />
  }
  return (
    <ul className="space-y-1">
      {logs.map((log) => (
        <li key={log.path} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
          <span className="font-mono text-xs break-all">{log.path}</span>
          <a
            href={endpoints.runArtifact(ulid, log.path)}
            target="_blank"
            rel="noreferrer"
            className="text-muted-foreground hover:text-foreground"
            title="View"
          >
            <Download size={14} />
          </a>
        </li>
      ))}
    </ul>
  )
}

export default function RunDetailPage() {
  const { ulid } = useParams({ from: '/runs/$ulid' })
  const runQuery = useRun(ulid)
  const artifactsQuery = useRunArtifacts(ulid)
  const run = runQuery.data as RunDetailShape | undefined

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title={run?.experiment_name ? `${run.experiment_name} · ${ulid.slice(0, 8)}` : ulid}
        description="Run details"
      />

      <AsyncBoundary
        isPending={runQuery.isPending}
        isError={runQuery.isError}
        error={runQuery.error}
        onRetry={() => runQuery.refetch()}
        errorFallbackMessage="Failed to load run."
        loadingFallback={<Skeleton className="h-48 w-full" />}
        emptyIcon={Play}
      >
        {run && (
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="test-results">Test Results</TabsTrigger>
              <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
              <TabsTrigger value="logs">Logs</TabsTrigger>
            </TabsList>
            <TabsContent value="overview">
              <OverviewTab run={run} />
            </TabsContent>
            <TabsContent value="test-results">
              <TestResultsTab results={run.test_results ?? []} />
            </TabsContent>
            <TabsContent value="artifacts">
              <AsyncBoundary
                isPending={artifactsQuery.isPending}
                isError={artifactsQuery.isError}
                error={artifactsQuery.error}
                onRetry={() => artifactsQuery.refetch()}
                errorFallbackMessage="Failed to load artifacts."
                loadingFallback={<Skeleton className="h-24 w-full" />}
              >
                <ArtifactsTab ulid={ulid} artifacts={artifactsQuery.data ?? []} />
              </AsyncBoundary>
            </TabsContent>
            <TabsContent value="logs">
              <AsyncBoundary
                isPending={artifactsQuery.isPending}
                isError={artifactsQuery.isError}
                error={artifactsQuery.error}
                onRetry={() => artifactsQuery.refetch()}
                errorFallbackMessage="Failed to load logs."
                loadingFallback={<Skeleton className="h-24 w-full" />}
              >
                <LogsTab ulid={ulid} artifacts={artifactsQuery.data ?? []} />
              </AsyncBoundary>
            </TabsContent>
          </Tabs>
        )}
      </AsyncBoundary>
    </div>
  )
}
