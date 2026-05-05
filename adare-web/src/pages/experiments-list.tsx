import { useState } from 'react'
import { CheckSquare, Copy, FlaskConical, Link2, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
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
              <TableHead>Environments</TableHead>
              <TableHead>Tags</TableHead>
              <TableHead>Runs</TableHead>
              <TableHead className="w-40 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((exp) => {
              const project = projectPathOf(exp) || '—'
              const tags: string[] = Array.isArray(exp.tags) ? exp.tags : []
              const runCount = (exp as { run_count?: number }).run_count
              const envNames: string[] = exp.environment_names ?? []
              return (
                <TableRow key={exp.name} className="hover:bg-muted/50">
                  <TableCell className="font-medium">{exp.name}</TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{project}</span>
                  </TableCell>
                  <TableCell>
                    {envNames.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {envNames.map((name) => (
                          <Badge key={name} variant="outline">
                            {name}
                          </Badge>
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
            {data.length} experiment{data.length === 1 ? '' : 's'}
          </TableCaption>
        </Table>
      )}

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
