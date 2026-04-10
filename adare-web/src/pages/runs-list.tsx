import { Play, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge, statusToVariant } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'
import { useRuns } from '@/api/hooks/use-runs'
import { formatDateTime, formatDuration } from '@/lib/formatters'

// Narrower view of the RunInfo shape returned by the backend
interface RunRow {
  ulid: string
  experiment_name?: string
  environment_name?: string
  start_time?: string
  duration_seconds?: number
  status?: string
  overall_result?: string
  published?: boolean
}

const SKELETON_ROWS = 5
const COLUMNS = 7

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

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Runs" description="Experiment execution history" />

      {isPending && <LoadingTable />}

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-6 flex items-center gap-4">
            <p className="text-sm text-destructive flex-1">
              {(error as Error)?.message ?? 'Failed to load runs.'}
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw size={14} />
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {!isPending && !isError && data?.length === 0 && (
        <EmptyState
          icon={Play}
          title="No runs yet"
          description="Run an experiment to see results here."
        />
      )}

      {!isPending && !isError && data && data.length > 0 && (
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
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data as unknown as RunRow[]).map((run) => (
              <TableRow key={run.ulid} className="hover:bg-muted/50">
                <TableCell>
                  <Badge variant={statusToVariant(run.status ?? null)}>
                    {run.status ?? '—'}
                  </Badge>
                </TableCell>
                <TableCell>{run.experiment_name ?? '—'}</TableCell>
                <TableCell>{run.environment_name || '—'}</TableCell>
                <TableCell>{formatDateTime(run.start_time)}</TableCell>
                <TableCell>{formatDuration(run.duration_seconds)}</TableCell>
                <TableCell>{run.overall_result || '—'}</TableCell>
                <TableCell>
                  <Badge variant={run.published ? 'success' : 'outline'}>
                    {run.published ? 'Yes' : 'No'}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>{data.length} run{data.length === 1 ? '' : 's'}</TableCaption>
        </Table>
      )}
    </div>
  )
}
