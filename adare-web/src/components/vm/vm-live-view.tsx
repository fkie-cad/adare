import { useCallback, useRef, useState } from 'react'
import { Loader2, MonitorOff, RefreshCw, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { useVmSpice, buildVmWsUrl } from '@/api/hooks/use-vms'
import {
  RemoteDesktopCanvas,
  type RemoteDesktopHandle,
} from '@/features/vm-viewer/RemoteDesktopCanvas'
import { useVmDisplay } from '@/features/vm-viewer/useVmDisplay'
import { useVmInput, type VmSurface } from '@/features/vm-viewer/useVmInput'
import { cn } from '@/lib/utils'

interface VmLiveViewProps {
  vmName: string
  /** `false` (default) enables keyboard/mouse control; `true` starts read-only. */
  viewOnly?: boolean
  className?: string
}

/**
 * Interactive in-app live view of a running VM.
 *
 * Renders the ADARE-owned SPICE viewer: an OffscreenCanvas fed by binary frames
 * over a same-origin WebSocket (`/ws/vm/<uuid>`), which ADARE proxies to
 * VirtualSpice internally. No cross-origin `<iframe>`, no `:8081` from the
 * browser, and no mixed-content problem over HTTPS. Keyboard/mouse input is
 * captured on the canvas and streamed back on the same socket (unless
 * `viewOnly`). Click into the screen to give it keyboard focus.
 */
export function VmLiveView({ vmName, viewOnly = false, className }: VmLiveViewProps) {
  const { data: spice, isLoading, refetch, isFetching } = useVmSpice(vmName, viewOnly)

  const canvasRef = useRef<RemoteDesktopHandle>(null)
  const [surface, setSurface] = useState<VmSurface | null>(null)

  const wsUrl = spice ? buildVmWsUrl(spice.ws_path) : null
  const { status, reconnect, send } = useVmDisplay(wsUrl, canvasRef)
  useVmInput({ canvasRef, send, surface, viewOnly })

  const handleSurface = useCallback((width: number, height: number) => {
    setSurface({ width, height })
  }, [])

  const handleReload = useCallback(() => {
    refetch()
    reconnect()
  }, [refetch, reconnect])

  const handlePopOut = useCallback(() => {
    window.open(
      `/vm/watch?name=${encodeURIComponent(vmName)}&view_only=${viewOnly}`,
      '_blank',
    )
  }, [vmName, viewOnly])

  const connecting = status === 'connecting' && !!wsUrl

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-sm font-medium truncate">{vmName}</span>
        <span className="text-xs text-muted-foreground hidden sm:inline">
          {viewOnly ? 'View only' : 'Click into the screen to control it'}
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
            onClick={handlePopOut}
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
        ) : spice ? (
          <>
            <RemoteDesktopCanvas
              ref={canvasRef}
              onSurface={handleSurface}
              className="absolute inset-0"
            />
            {(connecting || status === 'disconnected' || status === 'error') && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <span className="flex items-center gap-2 rounded-md bg-background/80 px-3 py-1.5 text-xs text-muted-foreground">
                  {connecting ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      Connecting…
                    </>
                  ) : status === 'error' ? (
                    'Connection error — retrying…'
                  ) : (
                    'Reconnecting…'
                  )}
                </span>
              </div>
            )}
          </>
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
