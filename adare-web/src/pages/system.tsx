import { Link } from '@tanstack/react-router'
import { Activity, MonitorPlay } from 'lucide-react'
import { PageHeader } from '@/components/layout/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ResourceTiles, ResourceTilesSkeleton } from '@/components/system/resource-tiles'
import { CapacityCard } from '@/components/system/capacity-card'
import { HistoryCard } from '@/components/system/history-card'
import { StorageCard } from '@/components/system/storage-card'
import {
  useRunUsage,
  useSystemCapacity,
  useSystemResources,
  useSystemStorage,
  type RunningVm,
} from '@/api/hooks/use-system'
import { formatBytes, formatDateTime, formatDuration, formatRelativeTime } from '@/lib/formatters'

function RssCell({ vm }: { vm: RunningVm }) {
  const guestBytes = vm.memory_mb ? vm.memory_mb * 1024 ** 2 : null
  const share = guestBytes ? Math.min(100, (100 * vm.rss_bytes) / guestBytes) : null
  return (
    <div className="flex items-center justify-end gap-2">
      {share != null && (
        <div className="h-1.5 w-16 rounded-full bg-series-2/15" title={`${Math.round(share)}% of guest RAM touched`}>
          <div className="h-full rounded-full bg-series-2" style={{ width: `${share}%` }} />
        </div>
      )}
      <span className="tabular-nums">{formatBytes(vm.rss_bytes)}</span>
    </div>
  )
}

function RunningVmsCard({ vms }: { vms: RunningVm[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <MonitorPlay className="h-5 w-5" aria-hidden />
          Running VMs
        </CardTitle>
        <CardDescription>Every QEMU process on this host: experiment runs, dev sessions and image builds.</CardDescription>
      </CardHeader>
      <CardContent>
        {vms.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No VMs running.</p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Run</TableHead>
                  <TableHead className="text-right">RAM (resident)</TableHead>
                  <TableHead className="text-right">CPU</TableHead>
                  <TableHead>Guest</TableHead>
                  <TableHead>Up</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {vms.map((vm) => (
                  <TableRow key={vm.pid}>
                    <TableCell className="max-w-[280px] truncate font-mono text-xs" title={vm.name}>
                      {vm.instance_id ? (
                        <Link to="/vms/$instanceId" params={{ instanceId: vm.instance_id }} className="hover:underline">
                          {vm.name}
                        </Link>
                      ) : (
                        vm.name
                      )}
                    </TableCell>
                    <TableCell>
                      {vm.experiment_run_id ? (
                        <Link
                          to="/runs/$ulid"
                          params={{ ulid: vm.experiment_run_id }}
                          className="font-mono text-xs hover:underline"
                        >
                          {vm.experiment_run_id.slice(-8)}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <RssCell vm={vm} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{Math.round(vm.cpu_percent)}%</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {vm.cpus ?? '?'} vCPU · {vm.memory_mb ? formatBytes(vm.memory_mb * 1024 ** 2, 0) : '?'}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatRelativeTime(vm.started_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function RunUsageCard() {
  const { data, isPending } = useRunUsage(50)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Activity className="h-5 w-5" aria-hidden />
          What runs actually used
        </CardTitle>
        <CardDescription>
          Measured on each run's VM while it ran. These numbers size the capacity estimate above.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? null : !data?.length ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No measured runs yet. Start an experiment run and its peak RAM, CPU and disk show up here.
          </p>
        ) : (
          <div className="max-h-[420px] overflow-auto rounded-md border">
            <Table>
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead>Started</TableHead>
                  <TableHead>Environment</TableHead>
                  <TableHead>Experiment</TableHead>
                  <TableHead className="text-right">Peak RAM</TableHead>
                  <TableHead className="text-right">Avg CPU</TableHead>
                  <TableHead className="text-right">Disk</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="text-sm">
                      <Link to="/runs/$ulid" params={{ ulid: u.experiment_run_id }} className="hover:underline">
                        {formatDateTime(u.started_at)}
                      </Link>
                    </TableCell>
                    <TableCell>{u.environment_name ?? '—'}</TableCell>
                    <TableCell>
                      {u.experiment_name ?? '—'}
                      {u.machine && <span className="ml-1 text-xs text-muted-foreground">({u.machine})</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatBytes(u.peak_rss_bytes)}
                      {u.vm_memory_mb && (
                        <span className="text-xs text-muted-foreground"> / {formatBytes(u.vm_memory_mb * 1024 ** 2, 0)}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{(u.avg_cpu_percent / 100).toFixed(1)} cores</TableCell>
                    <TableCell className="text-right tabular-nums">{formatBytes(u.disk_bytes)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatDuration(u.duration_seconds)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function SystemPage() {
  const resources = useSystemResources()
  const capacity = useSystemCapacity()
  const storage = useSystemStorage()
  const disk = resources.data?.disks[resources.data.disks.length - 1]

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="System"
        description="What this host has, what ADARE's VMs use, and how many more runs fit."
      />

      {resources.isError ? (
        <p className="text-sm text-destructive">{(resources.error as Error).message}</p>
      ) : resources.data ? (
        <ResourceTiles data={resources.data} reclaimableBytes={storage.data?.reclaimable_bytes} />
      ) : (
        <ResourceTilesSkeleton />
      )}

      <CapacityCard data={capacity.data} isPending={capacity.isPending} />
      {resources.data && <RunningVmsCard vms={resources.data.vms} />}
      <HistoryCard />
      <StorageCard data={storage.data} isPending={storage.isPending} disk={disk} />
      <RunUsageCard />
    </div>
  )
}
