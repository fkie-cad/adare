import { useMemo, useState } from 'react'
import { Cpu, Gauge, HardDrive, MemoryStick, OctagonAlert, Search } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBytes } from '@/lib/formatters'
import { cn } from '@/lib/utils'
import type { Capacity, EnvironmentCapacity } from '@/api/hooks/use-system'

const LIMIT_ICON = { memory: MemoryStick, cpu: Cpu, disk: HardDrive } as const
const LIMIT_LABEL = { memory: 'RAM', cpu: 'CPU', disk: 'Disk' } as const

function FitsCell({ env }: { env: EnvironmentCapacity }) {
  if (env.fits === 0) {
    return (
      <span className="inline-flex items-center gap-1 font-semibold">
        <OctagonAlert className="h-4 w-4 text-status-critical" aria-hidden />
        None
      </span>
    )
  }
  return <span className="text-lg font-semibold tabular-nums">{env.fits}</span>
}

function LimitedBy({ env }: { env: EnvironmentCapacity }) {
  const Icon = LIMIT_ICON[env.limited_by]
  const by = { memory: env.fits_by_memory, cpu: env.fits_by_cpu, disk: env.fits_by_disk }
  return (
    <span
      className="inline-flex items-center gap-1.5 text-sm"
      title={`RAM allows ${by.memory}, CPU ${by.cpu}, disk ${by.disk}`}
    >
      <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
      {LIMIT_LABEL[env.limited_by]}
    </span>
  )
}

export function CapacityCard({ data, isPending }: { data?: Capacity; isPending: boolean }) {
  const [query, setQuery] = useState('')
  const rows = useMemo(
    () =>
      (data?.environments ?? []).filter((e) => e.environment.toLowerCase().includes(query.trim().toLowerCase())),
    [data, query],
  )
  const measured = (data?.environments ?? []).filter((e) => e.need.source === 'measured').length

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between sm:space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Gauge className="h-5 w-5" aria-hidden />
            How many more runs fit right now
          </CardTitle>
          <CardDescription>
            {data ? (
              <>
                Free for new runs: <strong className="text-foreground">{formatBytes(data.headroom.memory_bytes)}</strong>{' '}
                RAM, <strong className="text-foreground">{data.headroom.cpu_cores.toFixed(1)}</strong> cores,{' '}
                <strong className="text-foreground">{formatBytes(data.headroom.disk_bytes)}</strong> disk, after keeping{' '}
                {Math.round(data.reserve.memory_fraction * 100)}% RAM and {Math.round(data.reserve.disk_fraction * 100)}%
                disk for the host.
              </>
            ) : (
              'Measuring headroom…'
            )}
          </CardDescription>
        </div>
        <div className="relative w-full sm:w-56">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter environments"
            className="pl-8"
            aria-label="Filter environments"
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="max-h-[420px] overflow-auto rounded-md border">
            <Table>
              <TableHeader className="sticky top-0 bg-card">
                <TableRow>
                  <TableHead>Environment</TableHead>
                  <TableHead className="text-right">Fits</TableHead>
                  <TableHead>Limited by</TableHead>
                  <TableHead className="text-right">RAM / run</TableHead>
                  <TableHead className="text-right">Cores / run</TableHead>
                  <TableHead className="text-right">Disk / run</TableHead>
                  <TableHead>Based on</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((env) => (
                  <TableRow key={env.environment}>
                    <TableCell className="font-medium">
                      {env.environment}
                      {env.platform && <span className="ml-2 text-xs text-muted-foreground">{env.platform}</span>}
                    </TableCell>
                    <TableCell className="text-right">
                      <FitsCell env={env} />
                    </TableCell>
                    <TableCell>
                      <LimitedBy env={env} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatBytes(env.need.memory_bytes)}</TableCell>
                    <TableCell className="text-right tabular-nums">{env.need.cpu_cores.toFixed(1)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatBytes(env.need.disk_bytes)}</TableCell>
                    <TableCell
                      className={cn('text-sm', env.need.source === 'configured' && 'text-muted-foreground')}
                    >
                      {env.need.source === 'measured'
                        ? `${env.need.measured_runs} measured run${env.need.measured_runs === 1 ? '' : 's'}`
                        : 'configured size'}
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="py-6 text-center text-muted-foreground">
                      No environments match.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          {measured === 0
            ? 'No run has been measured yet, so needs come from configured sizes (8 GiB RAM for Windows, 4 GiB otherwise, half the vCPUs busy). Every experiment run records what its VM actually used from now on.'
            : `${measured} environment${measured === 1 ? '' : 's'} sized from measured runs (peak RAM, typical CPU, largest disk); the rest from configured sizes.`}
        </p>
      </CardContent>
    </Card>
  )
}
