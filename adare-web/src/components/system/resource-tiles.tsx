import { Link } from '@tanstack/react-router'
import { Cpu, HardDrive, MemoryStick, MonitorPlay } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Meter, SeverityLabel, severityOf } from '@/components/system/meter'
import { formatBytes, formatPercent } from '@/lib/formatters'
import type { SystemResources } from '@/api/hooks/use-system'

interface TileProps {
  icon: React.ElementType
  label: string
  value: string
  detail: React.ReactNode
  percent?: number
  meter?: React.ReactNode
}

function Tile({ icon: Icon, label, value, detail, percent, meter }: TileProps) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <Icon className="h-4 w-4" aria-hidden />
            {label}
          </span>
          {percent != null && <SeverityLabel severity={severityOf(percent)} />}
        </div>
        <div className="text-3xl font-semibold tracking-tight">{value}</div>
        {meter}
        <div className="text-xs text-muted-foreground">{detail}</div>
      </CardContent>
    </Card>
  )
}

export function ResourceTilesSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <CardContent className="space-y-3 p-5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-2 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/** CPU, memory, disk and running VMs as a KPI row (System page and home dashboard). */
export function ResourceTiles({ data, reclaimableBytes }: { data: SystemResources; reclaimableBytes?: number }) {
  const { cpu, memory, disks, vm_totals: vms } = data
  const memPercent = (100 * memory.used_bytes) / memory.total_bytes
  const vmPercent = (100 * vms.rss_bytes) / memory.total_bytes
  const disk = disks[disks.length - 1]

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile
        icon={Cpu}
        label="CPU"
        value={formatPercent(cpu.percent)}
        percent={cpu.percent}
        meter={<Meter percent={cpu.percent} label="CPU load" />}
        detail={
          <>
            {cpu.count} cores
            {cpu.load_average && <> · load {cpu.load_average.map((l) => l.toFixed(1)).join(' / ')}</>}
          </>
        }
      />
      <Tile
        icon={MemoryStick}
        label="Memory"
        value={formatBytes(memory.used_bytes)}
        percent={memPercent}
        meter={
          <Meter
            percent={memPercent}
            label="Memory used"
            segments={[{ value: vmPercent, className: 'bg-series-2', label: 'ADARE VMs' }]}
          />
        }
        detail={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>of {formatBytes(memory.total_bytes)}</span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-series-2" aria-hidden />
              VMs {formatBytes(vms.rss_bytes)}
            </span>
            <span>{formatBytes(memory.available_bytes)} available</span>
          </span>
        }
      />
      {disk ? (
        <Tile
          icon={HardDrive}
          label="Disk"
          value={formatBytes(disk.free_bytes)}
          percent={disk.percent}
          meter={<Meter percent={disk.percent} label="Disk used" />}
          detail={
            <>
              free of {formatBytes(disk.total_bytes)} ({formatPercent(disk.percent)} used)
              {reclaimableBytes ? (
                <>
                  {' · '}
                  <Link to="/system" hash="storage" className="font-medium text-foreground underline-offset-2 hover:underline">
                    {formatBytes(reclaimableBytes)} reclaimable
                  </Link>
                </>
              ) : null}
            </>
          }
        />
      ) : (
        <Tile icon={HardDrive} label="Disk" value="—" detail="ADARE state directory not found" />
      )}
      <Tile
        icon={MonitorPlay}
        label="Running VMs"
        value={String(vms.count)}
        detail={
          vms.count ? (
            <>
              {formatBytes(vms.rss_bytes)} RAM · {(vms.cpu_percent / 100).toFixed(1)} cores busy
            </>
          ) : (
            'No QEMU VMs running'
          )
        }
      />
    </div>
  )
}
