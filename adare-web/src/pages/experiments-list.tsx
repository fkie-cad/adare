import { useState } from 'react'
import { CheckSquare, Copy, FlaskConical, Link2, Plus, Trash2 } from 'lucide-react'
import { Link } from '@tanstack/react-router'
import { PageHeader } from '@/components/layout/page-header'
import { AsyncBoundary } from '@/components/layout/async-boundary'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CreateExperimentDialog } from '@/components/dialogs/create-experiment-dialog'
import { CloneExperimentDialog } from '@/components/dialogs/clone-experiment-dialog'
import { LinkEnvironmentsDialog } from '@/components/dialogs/link-environments-dialog'
import {
  useExperiments,
  useRemoveExperiment,
  useValidateExperiment,
  type Experiment,
} from '@/api/hooks/use-experiments'
import { toast } from '@/components/ui/toast'

const SKELETON_ROWS = 5
const COLUMNS = 6

function LoadingTable() {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Project</TableHead>
          <TableHead>Environments</TableHead>
          <TableHead>Tags</TableHead>
          <TableHead>Runs</TableHead>
          <TableHead className="w-40 text-right">Actions</TableHead>
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

function projectPathOf(exp: Experiment): string {
  const p = (exp as { project_path?: string; project?: string })
  return String(p.project_path ?? p.project ?? '')
}

export default function ExperimentsListPage() {
  const { data, isPending, isError, error, refetch } = useExperiments()
  const removeMutation = useRemoveExperiment()
  const validateMutation = useValidateExperiment()

  const [createOpen, setCreateOpen] = useState(false)
  const [cloneTarget, setCloneTarget] = useState<Experiment | null>(null)
  const [linkTarget, setLinkTarget] = useState<Experiment | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Experiment | null>(null)

  const handleDelete = () => {
    if (!deleteTarget) return
    removeMutation.mutate(
      {
        name: deleteTarget.name,
        request: { project_path: projectPathOf(deleteTarget), force: true },
      },
      {
        onSuccess: () => {
          toast.success('Experiment removed', deleteTarget.name)
          setDeleteTarget(null)
        },
        onError: (err) => {
          toast.error('Failed to remove experiment', (err as Error)?.message)
        },
      },
    )
  }

  const handleValidate = (exp: Experiment) => {
    validateMutation.mutate(
      {
        name: exp.name,
        request: { project_path: projectPathOf(exp) },
      },
      {
        onSuccess: () => toast.success('Experiment valid', exp.name),
        onError: (err) =>
          toast.error(`Validation failed: ${exp.name}`, (err as Error)?.message),
      },
    )
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Experiments"
        description="Defined experiment configurations"
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={16} />
            New experiment
          </Button>
        }
      />

      <AsyncBoundary
        isPending={isPending}
        isError={isError}
        error={error}
        onRetry={() => refetch()}
        errorFallbackMessage="Failed to load experiments."
        loadingFallback={<LoadingTable />}
        isEmpty={data?.length === 0}
        emptyIcon={FlaskConical}
        emptyTitle="No experiments yet"
        emptyDescription="Create an experiment to get started."
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Project</TableHead>
              <TableHead>Environments</TableHead>
              <TableHead>Tags</TableHead>
              <TableHead>Runs</TableHead>
              <TableHead className="w-40 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data ?? []).map((exp) => {
              const project = projectPathOf(exp) || '—'
              const tags: string[] = Array.isArray(exp.tags) ? exp.tags : []
              const runCount = (exp as { run_count?: number }).run_count
              const envNames: string[] = exp.environment_names ?? []
              return (
                <TableRow key={exp.name} className="hover:bg-muted/50">
                  <TableCell className="font-medium">
                    <Link to="/experiments/$name" params={{ name: exp.name }} className="hover:underline">
                      {exp.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{project}</span>
                  </TableCell>
                  <TableCell>
                    {envNames.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {envNames.map((name) => (
                          <Link key={name} to="/environments/$name" params={{ name }}>
                            <Badge variant="outline" className="hover:bg-accent">
                              {name}
                            </Badge>
                          </Link>
                        ))}
                      </div>
                    ) : (
                      '—'
                    )}
                  </TableCell>
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
                  <TableCell>{typeof runCount === 'number' ? runCount : '—'}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Link environments"
                        onClick={() => setLinkTarget(exp)}
                      >
                        <Link2 size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Clone experiment"
                        onClick={() => setCloneTarget(exp)}
                      >
                        <Copy size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Validate experiment"
                        onClick={() => handleValidate(exp)}
                      >
                        <CheckSquare size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Delete experiment"
                        onClick={() => setDeleteTarget(exp)}
                      >
                        <Trash2 size={16} />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
          <TableCaption>
            {(data ?? []).length} experiment{(data ?? []).length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      </AsyncBoundary>

      <CreateExperimentDialog open={createOpen} onOpenChange={setCreateOpen} />

      <CloneExperimentDialog
        open={!!cloneTarget}
        onOpenChange={(open) => !open && setCloneTarget(null)}
        source={cloneTarget}
      />

      <LinkEnvironmentsDialog
        open={!!linkTarget}
        onOpenChange={(open) => !open && setLinkTarget(null)}
        experiment={linkTarget}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Remove experiment"
        description={
          deleteTarget
            ? `Are you sure you want to remove "${deleteTarget.name}"? This cannot be undone.`
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
