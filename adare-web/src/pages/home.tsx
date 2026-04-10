import { FolderKanban, FlaskConical, Play } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useProjects } from '@/api/hooks/use-projects'
import { useExperiments } from '@/api/hooks/use-experiments'
import { useRuns } from '@/api/hooks/use-runs'

interface StatCardProps {
  title: string
  icon: React.ReactNode
  count: number | undefined
  isPending: boolean
  isError: boolean
  onRetry: () => void
}

function StatCard({ title, icon, count, isPending, isError, onRetry }: StatCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
          <div className="text-muted-foreground">{icon}</div>
        </div>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-9 w-16" />
        ) : isError ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-destructive">Failed to load</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
              Retry
            </Button>
          </div>
        ) : (
          <p className="text-3xl font-bold">{count ?? 0}</p>
        )}
      </CardContent>
    </Card>
  )
}

export default function HomePage() {
  const projects = useProjects()
  const experiments = useExperiments()
  const runs = useRuns()

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Dashboard"
        description="Overview of your ADARE workspace"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          title="Projects"
          icon={<FolderKanban size={20} />}
          count={projects.data?.length}
          isPending={projects.isPending}
          isError={projects.isError}
          onRetry={() => projects.refetch()}
        />
        <StatCard
          title="Experiments"
          icon={<FlaskConical size={20} />}
          count={experiments.data?.length}
          isPending={experiments.isPending}
          isError={experiments.isError}
          onRetry={() => experiments.refetch()}
        />
        <StatCard
          title="Runs"
          icon={<Play size={20} />}
          count={runs.data?.length}
          isPending={runs.isPending}
          isError={runs.isError}
          onRetry={() => runs.refetch()}
        />
      </div>

      <p className="text-sm text-muted-foreground">
        Welcome to ADARE. Use the sidebar to browse runs, experiments, projects, and environments.
      </p>
    </div>
  )
}
