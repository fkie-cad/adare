import { useEffect, useState } from 'react'
import { Play, Trash2 } from 'lucide-react'
import { Link, useSearch } from '@tanstack/react-router'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { cn } from '@/lib/utils'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useRuns, useRemoveRun } from '@/api/hooks/use-runs'
import { formatDateTime, formatDuration } from '@/lib/formatters'
import { toast } from '@/components/ui/toast'

// Narrower view of the RunInfo shape returned by the backend
interface RunRow {
  ulid: string
  project_path?: string
  experiment_name?: string
  environment_name?: string
  start_time?: string
  duration_seconds?: number
  status?: string
  overall_result?: string
  published?: boolean
}

const SKELETON_ROWS = 5
const COLUMNS = 8

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Status</TableHead>
          <TableHead>Experiment</TableHead>
          <TableHead>Environment</TableHead>
          <TableHead>Started</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Result</TableHead>
          <TableHead>Published</TableHead>
          <TableHead className="w-16 text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
          <TableRow key={i}>
            {Array.from({ length: COLUMNS }).map((_, j) => (
              <TableCell key={j}>
                <Skeleton className="h-4 w-full" />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export default function RunsListPage() {
  const { data, isPending, isError, error, refetch } = useRuns()
  const removeMutation = useRemoveRun()
  const search = useSearch({ from: '/runs' }) as { focus?: string }
  const focusUlid = search.focus
  const [highlightUlid, setHighlightUlid] = useState<string | undefined>(focusUlid)
  const [deleteTarget, setDeleteTarget] = useState<RunRow | null>(null)

  useEffect(() => {
    setHighlightUlid(focusUlid)
    if (!focusUlid) return
    const t = setTimeout(() => setHighlightUlid(undefined), 5000)
    return () => clearTimeout(t)
  }, [focusUlid])

  const handleDelete = () => {
    if (!deleteTarget) return
    removeMutation.mutate(
      { ulid: deleteTarget.ulid, projectPath: deleteTarget.project_path },
      {
        onSuccess: () => {
          toast.success('Run removed', deleteTarget.ulid)
          setDeleteTarget(null)
        },
        onError: (err) => {
          toast.error('Failed to remove run', (err as Error)?.message)
        },
      },
    )
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Runs" description="Experiment execution history" />

      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load runs."
        loadingFallback={<LoadingTable />}
        isEmpty={data?.length === 0}
        emptyIcon={Play}
        emptyTitle="No runs yet"
        emptyDescription="Run an experiment to see results here."
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Status</TableHead>
              <TableHead>Experiment</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Published</TableHead>
              <TableHead className="w-16 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {((data ?? []) as unknown as RunRow[]).map((run) => (
              <TableRow
                key={run.ulid}
                className={cn(
                  'hover:bg-muted/50',
                  highlightUlid === run.ulid && 'bg-primary/10 ring-2 ring-primary',
                )}
              >
                <TableCell>
                  <Link to="/runs/$ulid" params={{ ulid: run.ulid }} className="inline-flex">
                    <Badge variant={statusToVariant(run.status ?? null)}>
                      {run.status ?? '—'}
                    </Badge>
                  </Link>
                </TableCell>
                <TableCell>
                  {run.experiment_name ? (
                    <Link
                      to="/experiments/$name"
                      params={{ name: run.experiment_name }}
                      className="hover:underline"
                    >
                      {run.experiment_name}
                    </Link>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>
                  {run.environment_name ? (
                    <Link
                      to="/environments/$name"
                      params={{ name: run.environment_name }}
                      className="hover:underline"
                    >
                      {run.environment_name}
                    </Link>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>{formatDateTime(run.start_time)}</TableCell>
                <TableCell>{formatDuration(run.duration_seconds)}</TableCell>
                <TableCell>{run.overall_result || '—'}</TableCell>
                <TableCell>
                  <Badge variant={run.published ? 'success' : 'outline'}>
                    {run.published ? 'Yes' : 'No'}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete run"
                    onClick={() => setDeleteTarget(run)}
                  >
                    <Trash2 size={16} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>{(data ?? []).length} run{(data ?? []).length === 1 ? '' : 's'}</TableCaption>
        </Table>
      </AsyncBoundary>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Remove run"
        description={
          deleteTarget
            ? `Are you sure you want to remove run "${deleteTarget.ulid}"? This cannot be undone.`
            : undefined
        }
        confirmLabel="Remove"
        variant="destructive"
        loading={removeMutation.isPending}
        onConfirm={handleDelete}
      />
    </div>
  )
}
