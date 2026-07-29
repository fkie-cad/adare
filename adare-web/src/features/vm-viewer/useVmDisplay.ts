import { useCallback, useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type { RemoteDesktopHandle } from './RemoteDesktopCanvas'

export type DisplayStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

const RECONNECT_DELAY_MS = 1500

/**
 * Owns the same-origin display WebSocket for a VM. Each incoming binary frame
 * is handed straight to the render worker (buffer transferred) — never through
 * React state, so a frame never triggers a re-render. Reconnects automatically
 * on unexpected drops until unmounted or `wsUrl` changes.
 */
export function useVmDisplay(
  wsUrl: string | null,
  canvasRef: RefObject<RemoteDesktopHandle | null>,
): { status: DisplayStatus; reconnect: () => void; send: (buf: ArrayBuffer) => void } {
  const [status, setStatus] = useState<DisplayStatus>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const closedByUsRef = useRef(false)
  // Bumped by reconnect() to force the connect effect to re-run.
  const [attempt, setAttempt] = useState(0)

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const reconnect = useCallback(() => {
    clearReconnect()
    setAttempt((n) => n + 1)
  }, [clearReconnect])

  // Stable sender for the input hook — writes to the live socket if open.
  const send = useCallback((buf: ArrayBuffer) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(buf)
    }
  }, [])

  useEffect(() => {
    if (!wsUrl) {
      setStatus('disconnected')
      return
    }

    closedByUsRef.current = false
    setStatus('connecting')

    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => setStatus('connected')

    ws.onmessage = (evt: MessageEvent) => {
      if (evt.data instanceof ArrayBuffer) {
        canvasRef.current?.postFrame(evt.data)
      }
    }

    ws.onerror = () => {
      if (!closedByUsRef.current) setStatus('error')
    }

    ws.onclose = () => {
      wsRef.current = null
      if (closedByUsRef.current) return
      setStatus('disconnected')
      // Auto-reconnect after a short delay.
      clearReconnect()
      reconnectTimerRef.current = setTimeout(() => setAttempt((n) => n + 1), RECONNECT_DELAY_MS)
    }

    return () => {
      closedByUsRef.current = true
      clearReconnect()
      ws.onopen = null
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
      wsRef.current = null
    }
  }, [wsUrl, attempt, canvasRef, clearReconnect])

  return { status, reconnect, send }
}
