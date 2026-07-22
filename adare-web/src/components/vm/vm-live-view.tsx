import { useState } from 'react'
import { Loader2, MonitorOff, RefreshCw, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { useVmWatchUrl } from '@/api/hooks/use-vms'
import { cn } from '@/lib/utils'

interface VmLiveViewProps {
  vmName: string
  /**
   * `true` (default) starts read-only: no keyboard/mouse control AND no
   * viewer-driven guest resolution change (forensically non-mutating, matching
   * the `adare vm watch` CLI default). `false` enables interactive control and
   * auto-resize. Users can still flip this in-iframe via the View Only toggle.
   */
  viewOnly?: boolean
  className?: string
}

/**
 * Interactive in-app live view of a running VM.
 *
 * Embeds VirtualSpice's own standalone `display.html` in a cross-origin
 * `<iframe>` pointed at `:8081`, reusing the backend name→URL resolver. The
 * iframe hosts the full VirtualSpice viewer (its own toolbar: view-only toggle,
 * clipboard, fullscreen, resolution, pause), so ADARE adds no `spice-client`
 * dependency and copies no viewer component.
 *
 * Caveats (cross-origin iframe):
 * - Keyboard capture: SPICE receives keys only while the iframe is focused —
 *   click into the screen first; the in-iframe fullscreen toolbar guarantees
 *   capture.
 * - `allow="fullscreen; clipboard-read; clipboard-write"` is required or those
 *   toolbar buttons silently no-op. No `sandbox` — SPICE needs scripts,
 *   clipboard and pointer-lock.
 * - The iframe loads `http://<host>:8081/...` directly from the browser (same
 *   assumption as the pop-out tab). If the backend resolves the VM but the
 *   browser can't reach `:8081` (remote/firewall), the iframe shows an
 *   undetectable error page. Over HTTPS an `http://:8081` frame is blocked as
 *   mixed content (both are HTTP today). Loading / "unavailable" states come
 *   from the resolver, not the iframe (cross-origin `onError` is unreliable).
 */
export function VmLiveView({ vmName, viewOnly = true, className }: VmLiveViewProps) {
  const { data: url, isLoading, refetch, isFetching } = useVmWatchUrl(vmName, viewOnly)
  // Cross-origin frames can't be `.reload()`-ed, so remount via a key bump.
  const [reloadKey, setReloadKey] = useState(0)

  const handleReload = () => {
    setReloadKey((k) => k + 1)
    refetch()
  }

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-sm font-medium truncate">{vmName}</span>
        <span className="text-xs text-muted-foreground hidden sm:inline">
          Click into the screen to control it
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleReload}
            disabled={isFetching}
            title="Re-establish the live connection"
          >
            <RefreshCw size={14} className={cn(isFetching && 'animate-spin')} />
            Reload
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => url && window.open(url, '_blank')}
            disabled={!url}
            title="Open the live view in a new tab"
          >
            <ExternalLink size={14} />
            Pop out
          </Button>
        </div>
      </div>

      <div className="relative flex-1 bg-black">
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 size={32} className="animate-spin text-muted-foreground" />
          </div>
        ) : url ? (
          <iframe
            key={reloadKey}
            src={url}
            title={`Live view of ${vmName}`}
            className="absolute inset-0 h-full w-full border-0"
            allow="fullscreen; clipboard-read; clipboard-write"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <EmptyState
              icon={MonitorOff}
              title="Live view unavailable"
              description="Is VirtualSpice running and the VM up?"
              action={
                <Button variant="outline" size="sm" onClick={handleReload}>
                  <RefreshCw size={14} />
                  Retry
                </Button>
              }
            />
          </div>
        )}
      </div>
    </div>
  )
}
