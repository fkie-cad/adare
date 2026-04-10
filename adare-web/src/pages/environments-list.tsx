import { Server, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { Button } from '@/components/ui/button'
import { useEnvironments } from '@/api/hooks/use-environments'

const SKELETON_ROWS = 5
const COLUMNS = 5

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>OS</TableHead>
          <TableHead>VM</TableHead>
          <TableHead>Project</TableHead>
          <TableHead>Sync</TableHead>
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

function SyncBadge({ synced }: { synced: unknown }) {
  if (synced === true) return <Badge variant="success">Synced</Badge>
  if (synced === false) return <Badge variant="warning">Unsynced</Badge>
  return <>—</>
}

export default function EnvironmentsListPage() {
  const { data, isPending, isError, error, refetch } = useEnvironments()

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="Environments" description="VM environments for running experiments" />

      {isPending && <LoadingTable />}

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-6 flex items-center gap-4">
            <p className="text-sm text-destructive flex-1">
              {(error as Error)?.message ?? 'Failed to load environments.'}
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
          icon={Server}
          title="No environments"
          description="Create an environment to run experiments against."
        />
      )}

      {!isPending && !isError && data && data.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>OS</TableHead>
              <TableHead>VM</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Sync</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((env) => (
              <TableRow key={env.name} className="hover:bg-muted/50">
                <TableCell className="font-medium">{env.name}</TableCell>
                <TableCell>{(env as any).os || '—'}</TableCell>
                <TableCell>
                  {env.vm_path ? (
                    <span className="font-mono text-xs">{env.vm_path}</span>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>
                  {env.project_path ? (
                    <span className="font-mono text-xs">{env.project_path}</span>
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>
                  <SyncBadge synced={(env as any).synced} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>
            {data.length} environment{data.length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      )}
    </div>
  )
}
