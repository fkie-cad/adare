import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Play, Trash2 } from 'lucide-react'
import { Link, useSearch } from '@tanstack/react-router'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { cn } from '@/lib/utils'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useRuns, useRemoveRun, isActiveRun, type Run } from '@/api/hooks/use-runs'
import { formatDateTime, formatDuration, parseTimestamp } from '@/lib/formatters'
import { toast } from '@/components/ui/toast'

const SKELETON_ROWS = 5
const COLUMNS = 8

type SortKey = 'status' | 'experiment' | 'environment' | 'started' | 'duration' | 'result' | 'published'
type SortDir = 'asc' | 'desc'
interface Sort {
  key: SortKey
  dir: SortDir
}

const DEFAULT_SORT: Sort = { key: 'started', dir: 'desc' }
/** Columns whose first click sorts descending (newest / longest / published first). */
const DESC_FIRST: ReadonlySet<SortKey> = new Set(['started', 'duration', 'published'])

const ULID_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

/** Creation time (ms) encoded in a ULID's first 10 characters, or 0 if it is not a ULID. */
function ulidTime(ulid: string): number {
  if (ulid.length !== 26) return 0
  let ms = 0
  for (const ch of ulid.slice(0, 10).toUpperCase()) {
    const v = ULID_ALPHABET.indexOf(ch)
    if (v < 0) return 0
    ms = ms * 32 + v
  }
  return ms
}

/** When the run started; a run still setting up has no start_time yet, so its ULID dates it. */
function startedAt(run: Run): number {
  return parseTimestamp(run.start_time)?.getTime() ?? ulidTime(run.ulid)
}

function sortValue(run: Run, key: SortKey): string | number {
  switch (key) {
    case 'status':
      return run.status ?? ''
    case 'experiment':
      return run.experiment_name ?? ''
    case 'environment':
      return run.environment_name ?? ''
    case 'started':
      return startedAt(run)
    case 'duration':
      return run.duration_seconds ?? 0
    case 'result':
      return run.result_status ?? ''
    case 'published':
      return run.published ? 1 : 0
  }
}

function sortRuns(runs: Run[], sort: Sort): Run[] {
  const sign = sort.dir === 'asc' ? 1 : -1
  return [...runs].sort((a, b) => {
    const va = sortValue(a, sort.key)
    const vb = sortValue(b, sort.key)
    const cmp =
      typeof va === 'number' && typeof vb === 'number'
        ? va - vb
        : String(va).localeCompare(String(vb), undefined, { sensitivity: 'base' })
    // Ties: newest first, whatever the column.
    return cmp !== 0 ? sign * cmp : startedAt(b) - startedAt(a)
  })
}

function SortableHead({
  label,
  column,
  sort,
  onSort,
  className,
}: {
  label: string
  column: SortKey
  sort: Sort
  onSort: (key: SortKey) => void
  className?: string
}) {
  const active = sort.key === column
  const Icon = !active ? ArrowUpDown : sort.dir === 'asc' ? ArrowUp : ArrowDown
  return (
    <TableHead
      className={className}
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={cn(
          'inline-flex items-center gap-1 hover:text-foreground',
          active && 'text-foreground',
        )}
      >
        {label}
        <Icon size={14} className={cn(!active && 'opacity-40')} />
      </button>
    </TableHead>
  )
}

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
  const [deleteTarget, setDeleteTarget] = useState<Run | null>(null)
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT)
  const runs = useMemo(() => sortRuns(data ?? [], sort), [data, sort])
  const activeCount = runs.filter(isActiveRun).length

  const handleSort = (key: SortKey) =>
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: DESC_FIRST.has(key) ? 'desc' : 'asc' },
    )

  useEffect(() => {
    setHighlightUlid(focusUlid)
    if (!focusUlid) return
    const t = setTimeout(() => setHighlightUlid(undefined), 5000)
    return () => clearTimeout(t)
  }, [focusUlid])

  const handleDelete = () => {
    if (!deleteTarget) return
    removeMutation.mutate(
      { ulid: deleteTarget.ulid },
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
              <SortableHead label="Status" column="status" sort={sort} onSort={handleSort} />
              <SortableHead label="Experiment" column="experiment" sort={sort} onSort={handleSort} />
              <SortableHead label="Environment" column="environment" sort={sort} onSort={handleSort} />
              <SortableHead label="Started" column="started" sort={sort} onSort={handleSort} />
              <SortableHead label="Duration" column="duration" sort={sort} onSort={handleSort} />
              <SortableHead label="Result" column="result" sort={sort} onSort={handleSort} />
              <SortableHead label="Published" column="published" sort={sort} onSort={handleSort} />
              <TableHead className="w-16 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
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
                <TableCell>{isActiveRun(run) && !run.end_time ? '—' : formatDuration(run.duration_seconds)}</TableCell>
                <TableCell>{run.result_status || '—'}</TableCell>
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
          <TableCaption>
            {runs.length} run{runs.length === 1 ? '' : 's'}
            {activeCount > 0 && ` · ${activeCount} active`}
          </TableCaption>
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
