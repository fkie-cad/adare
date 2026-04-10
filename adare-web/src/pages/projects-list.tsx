import { FolderKanban, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'
import { useProjects } from '@/api/hooks/use-projects'
import { formatDateTime } from '@/lib/formatters'

const SKELETON_ROWS = 5
const COLUMNS = 4

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Path</TableHead>
          <TableHead>Description</TableHead>
          <TableHead>Created</TableHead>
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

export default function ProjectsListPage() {
  const { data, isPending, isError, error, refetch } = useProjects()

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Projects" description="Organized collections of experiments and environments" />

      {isPending && <LoadingTable />}

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-6 flex items-center gap-4">
            <p className="text-sm text-destructive flex-1">
              {(error as Error)?.message ?? 'Failed to load projects.'}
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
          icon={FolderKanban}
          title="No projects"
          description="Add a project to organize your work."
        />
      )}

      {!isPending && !isError && data && data.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Path</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((project) => (
              <TableRow key={project.path} className="hover:bg-muted/50">
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{project.name}</span>
                    {(project as any).is_current === true && (
                      <Badge variant="secondary">Current</Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <span className="font-mono text-xs">{project.path}</span>
                </TableCell>
                <TableCell>{project.description || '—'}</TableCell>
                <TableCell>{formatDateTime((project as any).created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>
            {data.length} project{data.length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      )}
    </div>
  )
}
