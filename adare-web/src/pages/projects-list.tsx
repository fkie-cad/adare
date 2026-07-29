import { useState } from 'react'
import { FolderKanban, Plus, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CreateProjectDialog } from '@/components/dialogs/create-project-dialog'
import { useProjects, useDeleteProject, type Project } from '@/api/hooks/use-projects'
import { formatDateTime } from '@/lib/formatters'
import { toast } from '@/components/ui/toast'

const SKELETON_ROWS = 5
const COLUMNS = 5

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Path</TableHead>
          <TableHead>Description</TableHead>
          <TableHead>Created</TableHead>
          <TableHead className="w-24 text-right">Actions</TableHead>
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
  const deleteMutation = useDeleteProject()
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)

  const handleDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(
      { name: deleteTarget.name, path: String(deleteTarget.path) },
      {
        onSuccess: () => {
          toast.success('Project removed', deleteTarget.name)
          setDeleteTarget(null)
        },
        onError: (err) => {
          toast.error('Failed to remove project', (err as Error)?.message)
        },
      },
    )
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Projects"
        description="Organized collections of experiments and environments"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={16} />
            New project
          </Button>
        }
      />

      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load projects."
        loadingFallback={<LoadingTable />}
        isEmpty={data?.length === 0}
        emptyIcon={FolderKanban}
        emptyTitle="No projects"
        emptyDescription="Add a project to organize your work."
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Path</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-24 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((project) => (
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
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Delete project"
                    onClick={() => setDeleteTarget(project)}
                  >
                    <Trash2 size={16} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableCaption>
            {(data ?? []).length} project{(data ?? []).length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      </AsyncBoundary>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Remove project"
        description={
          deleteTarget
            ? `Are you sure you want to remove "${deleteTarget.name}"? This cannot be undone.`
            : undefined
        }
        confirmLabel="Remove"
        variant="destructive"
        loading={deleteMutation.isPending}
        onConfirm={handleDelete}
      />
    </div>
  )
}
