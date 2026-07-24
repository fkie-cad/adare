import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { cn } from '@/lib/utils'

export interface RemoteDesktopHandle {
  /** Forward a raw WS binary frame to the render worker (buffer is transferred). */
  postFrame: (buf: ArrayBuffer) => void
  /** The underlying canvas element (for input listeners / coord mapping). */
  getCanvas: () => HTMLCanvasElement | null
}

interface Props {
  /** Called when the guest surface (primary, id=0) reports its dimensions. */
  onSurface?: (width: number, height: number) => void
  className?: string
}

/**
 * Remote desktop canvas backed by an OffscreenCanvas render worker.
 *
 * The canvas is transferred to a module worker once on mount; frames are pushed
 * imperatively via the `postFrame` handle (never through React state, so no
 * re-render occurs per frame). The intrinsic canvas size tracks the guest
 * surface; CSS scales it to fit the container while preserving aspect ratio.
 */
export const RemoteDesktopCanvas = forwardRef<RemoteDesktopHandle, Props>(
  function RemoteDesktopCanvas({ onSurface, className }, ref) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const workerRef = useRef<Worker | null>(null)
    const transferredRef = useRef(false)
    const cleanupRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    // Keep the latest onSurface without re-running the mount effect.
    const onSurfaceRef = useRef(onSurface)
    onSurfaceRef.current = onSurface

    useImperativeHandle(
      ref,
      () => ({
        postFrame: (buf: ArrayBuffer) => {
          workerRef.current?.postMessage({ type: 'frame', data: buf }, [buf])
        },
        getCanvas: () => canvasRef.current,
      }),
      [],
    )

    useEffect(() => {
      const canvas = canvasRef.current
      if (!canvas) return

      // Cancel any pending deferred cleanup (React StrictMode re-fire).
      if (cleanupRef.current !== null) {
        clearTimeout(cleanupRef.current)
        cleanupRef.current = null
      }

      if (!transferredRef.current) {
        const worker = new Worker(new URL('./display.worker.ts', import.meta.url), {
          type: 'module',
        })

        const offscreen = canvas.transferControlToOffscreen()
        transferredRef.current = true
        worker.postMessage({ type: 'init', canvas: offscreen }, [offscreen])

        worker.onmessage = (e: MessageEvent) => {
          const msg = e.data
          if (msg?.type === 'surfaceCreate' && msg.surfaceId === 0) {
            onSurfaceRef.current?.(msg.width, msg.height)
          }
        }

        workerRef.current = worker
      }

      return () => {
        // Defer termination so a StrictMode remount can cancel it.
        cleanupRef.current = setTimeout(() => {
          workerRef.current?.terminate()
          workerRef.current = null
          transferredRef.current = false
        }, 0)
      }
    }, [])

    return (
      <canvas
        ref={canvasRef}
        className={cn('block h-full w-full object-contain', className)}
        style={{ imageRendering: 'pixelated' }}
      />
    )
  },
)
