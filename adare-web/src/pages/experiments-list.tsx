import { FlaskConical, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'
import { useExperiments } from '@/api/hooks/use-experiments'

const SKELETON_ROWS = 5
const COLUMNS = 4

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Project</TableHead>
          <TableHead>Tags</TableHead>
          <TableHead>Runs</TableHead>
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

export default function ExperimentsListPage() {
  const { data, isPending, isError, error, refetch } = useExperiments()

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Experiments" description="Defined experiment configurations" />

      {isPending && <LoadingTable />}

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-6 flex items-center gap-4">
            <p className="text-sm text-destructive flex-1">
              {(error as Error)?.message ?? 'Failed to load experiments.'}
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
          icon={FlaskConical}
          title="No experiments yet"
          description="Create an experiment to get started."
        />
      )}

      {!isPending && !isError && data && data.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Tags</TableHead>
              <TableHead>Runs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((exp) => {
              const project = (exp as any).project_path || (exp as any).project || '—'
              const tags: string[] = Array.isArray(exp.tags) ? exp.tags : []
              const runCount = (exp as any).run_count
              return (
                <TableRow key={exp.name} className="hover:bg-muted/50">
                  <TableCell className="font-medium">{exp.name}</TableCell>
                  <TableCell>{project}</TableCell>
                  <TableCell>
                    {tags.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {tags.map((tag) => (
                          <Badge key={tag} variant="outline">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    {typeof runCount === 'number' ? runCount : '—'}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
          <TableCaption>
            {data.length} experiment{data.length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      )}
    </div>
  )
}
