import { useState } from 'react'
import { AlertTriangle, Check, Copy, Database, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StackedBar } from '@/components/system/stacked-bar'
import { useRefreshSystemStorage, type DiskInfo, type StorageReport } from '@/api/hooks/use-system'
import { formatBytes, formatRelativeTime } from '@/lib/formatters'

// Fixed slot per category, in the validated order: color follows the category, never its rank.
const CATEGORY_COLOR: Record<string, string> = {
  environment_disks: 'bg-series-1',
  run_disks: 'bg-series-2',
  templates: 'bg-series-3',
  caches: 'bg-series-4',
  isos: 'bg-series-5',
  other: 'bg-series-6',
}

const STATE_BADGE = {
  running: { variant: 'success', label: 'Running' },
  registered: { variant: 'outline', label: 'Registered' },
  orphaned: { variant: 'warning', label: 'No owner' },
} as const

const PRUNE_COMMAND = 'adare vm prune'
const OWNERS_SHOWN = 8

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(command)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="inline-flex items-center gap-1.5 rounded border bg-background px-2 py-0.5 font-mono text-xs hover:bg-muted"
      title="Copy command"
    >
      {command}
      {copied ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
    </button>
  )
}

export function StorageCard({ data, isPending, disk }: { data?: StorageReport; isPending: boolean; disk?: DiskInfo }) {
  const refresh = useRefreshSystemStorage()
  const [showAllOwners, setShowAllOwners] = useState(false)
  const adareTotal = data?.categories.reduce((sum, c) => sum + c.bytes, 0) ?? 0
  const orphaned = data?.disk_owners.filter((o) => o.state === 'orphaned') ?? []
  const owners = showAllOwners ? (data?.disk_owners ?? []) : (data?.disk_owners ?? []).slice(0, OWNERS_SHOWN)
  const maxProject = Math.max(1, ...(data?.projects ?? []).map((p) => p.bytes))

  return (
    <Card id="storage" className="scroll-mt-6">
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between sm:space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Database className="h-5 w-5" aria-hidden />
            Where the disk space goes
          </CardTitle>
          <CardDescription>
            {data ? (
              <>
                ADARE holds <strong className="text-foreground">{formatBytes(adareTotal)}</strong>
                {disk && <> of the {formatBytes(disk.used_bytes)} used on this disk</>}. Measured{' '}
                {formatRelativeTime(data.computed_at)}.
              </>
            ) : (
              'Measuring… this walks every VM disk and project, which takes a few seconds.'
            )}
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          <RefreshCw size={14} className={refresh.isPending ? 'animate-spin' : undefined} />
          Re-measure
        </Button>
      </CardHeader>
      <CardContent className="space-y-6">
        {isPending || !data ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <>
            <StackedBar
              total={adareTotal}
              format={(v) => formatBytes(v)}
              segments={data.categories.map((c) => ({
                key: c.key,
                label: c.label,
                value: c.bytes,
                colorClass: CATEGORY_COLOR[c.key] ?? 'bg-series-muted',
                detail: c.path,
              }))}
            />

            {orphaned.length > 0 && (
              <div className="flex flex-col gap-2 rounded-md border border-status-warning/50 bg-status-warning/10 p-3 text-sm sm:flex-row sm:items-center">
                <AlertTriangle className="h-4 w-4 shrink-0 text-status-warning" aria-hidden />
                <span className="flex-1">
                  <strong>{formatBytes(data.reclaimable_bytes)}</strong> of run disks in {orphaned.length} group
                  {orphaned.length === 1 ? '' : 's'} have no database owner (crashed or pre-overlay runs). Preview
                  what would be removed, then reclaim with <code className="font-mono">--force</code>:
                </span>
                <CopyCommand command={PRUNE_COMMAND} />
              </div>
            )}

            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Projects</h4>
                <ul className="space-y-2">
                  {data.projects.map((p) => (
                    <li key={p.path} className="space-y-1">
                      <div className="flex items-baseline justify-between gap-2 text-sm">
                        <span className="truncate font-medium" title={p.path}>
                          {p.name}
                        </span>
                        <span className="tabular-nums text-muted-foreground">{formatBytes(p.bytes)}</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-series-1/15">
                        <div
                          className="h-full rounded-full bg-series-1"
                          style={{ width: `${(100 * p.bytes) / maxProject}%` }}
                        />
                      </div>
                    </li>
                  ))}
                  {data.projects.length === 0 && <li className="text-sm text-muted-foreground">No projects.</li>}
                </ul>
              </div>

              <div className="space-y-2">
                <h4 className="text-sm font-medium">Run & dev-session disks by owner</h4>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Instance</TableHead>
                        <TableHead>State</TableHead>
                        <TableHead className="text-right">Size</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {owners.map((o) => {
                        const badge = STATE_BADGE[o.state]
                        return (
                          <TableRow key={o.name}>
                            <TableCell className="max-w-[260px] truncate font-mono text-xs" title={o.name}>
                              {o.name}
                            </TableCell>
                            <TableCell>
                              <Badge variant={badge.variant}>{badge.label}</Badge>
                              {o.instance_status && (
                                <span className="ml-2 text-xs text-muted-foreground">{o.instance_status}</span>
                              )}
                            </TableCell>
                            <TableCell className="text-right tabular-nums">{formatBytes(o.bytes)}</TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
                {data.disk_owners.length > OWNERS_SHOWN && (
                  <Button variant="ghost" size="sm" onClick={() => setShowAllOwners((v) => !v)}>
                    {showAllOwners ? 'Show fewer' : `Show all ${data.disk_owners.length}`}
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
