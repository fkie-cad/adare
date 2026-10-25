import { useMemo, useState } from 'react'
import { LineChart } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { TimeSeriesChart } from '@/components/system/time-series-chart'
import { useSystemHistory } from '@/api/hooks/use-system'
import { formatBytes, formatPercent } from '@/lib/formatters'
import { cn } from '@/lib/utils'

const RANGES = [
  { hours: 6, label: '6h' },
  { hours: 24, label: '24h' },
  { hours: 24 * 7, label: '7d' },
  { hours: 24 * 30, label: '30d' },
] as const

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">{title}</h4>
      {children}
    </div>
  )
}

export function HistoryCard() {
  const [hours, setHours] = useState<number>(24)
  const { data, isPending, isError, error } = useSystemHistory(hours)

  const chart = useMemo(() => {
    const points = data ?? []
    return {
      times: points.map((p) => new Date(p.taken_at)),
      cpu: points.map((p) => p.cpu_percent),
      memUsed: points.map((p) => p.memory_used_bytes),
      vmRss: points.map((p) => p.vm_rss_bytes),
      memTotal: points.length ? points[points.length - 1].memory_total_bytes : undefined,
      diskUsed: points.map((p) => p.disk_used_bytes),
      diskTotal: points.length ? points[points.length - 1].disk_total_bytes : undefined,
      vmCount: points.map((p) => p.vm_count),
    }
  }, [data])

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between sm:space-y-0">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-lg">
            <LineChart className="h-5 w-5" aria-hidden />
            Usage over time
          </CardTitle>
          <CardDescription>Sampled every minute while the web UI runs; kept for 30 days.</CardDescription>
        </div>
        <div className="inline-flex rounded-md border p-0.5" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button
              key={r.hours}
              type="button"
              aria-pressed={hours === r.hours}
              onClick={() => setHours(r.hours)}
              className={cn(
                'rounded px-3 py-1 text-sm transition-colors',
                hours === r.hours ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground hover:bg-muted',
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive">{(error as Error).message}</p>
        ) : chart.times.length < 2 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Not enough samples yet. The first points appear a couple of minutes after the web UI starts.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartPanel title="CPU">
              <TimeSeriesChart
                ariaLabel="Host CPU load over time"
                times={chart.times}
                series={[{ key: 'cpu', label: 'Host CPU', color: 'var(--color-series-1)', values: chart.cpu }]}
                formatValue={formatPercent}
                yMax={100}
              />
            </ChartPanel>
            <ChartPanel title="Memory">
              <TimeSeriesChart
                ariaLabel="Host memory used and ADARE VM memory over time"
                times={chart.times}
                series={[
                  { key: 'used', label: 'Host used', color: 'var(--color-series-1)', values: chart.memUsed },
                  { key: 'vms', label: 'ADARE VMs', color: 'var(--color-series-2)', values: chart.vmRss },
                ]}
                formatValue={(v) => formatBytes(v, 0)}
                yMax={chart.memTotal}
              />
            </ChartPanel>
            <ChartPanel title="Disk used">
              <TimeSeriesChart
                ariaLabel="Disk used over time"
                times={chart.times}
                series={[{ key: 'disk', label: 'Disk used', color: 'var(--color-series-1)', values: chart.diskUsed }]}
                formatValue={(v) => formatBytes(v, 0)}
                yMax={chart.diskTotal}
              />
            </ChartPanel>
            <ChartPanel title="Running VMs">
              <TimeSeriesChart
                ariaLabel="Number of running VMs over time"
                times={chart.times}
                series={[{ key: 'vms', label: 'VMs', color: 'var(--color-series-1)', values: chart.vmCount }]}
                formatValue={(v) => String(Math.round(v))}
                integer
              />
            </ChartPanel>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
