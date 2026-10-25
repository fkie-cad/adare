import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { terminalSocketUrl } from '@/api/hooks/use-terminals'

// Always dark, like an IDE's terminal: Claude Code's TUI is designed for it.
const THEME = {
  background: '#0b1416',
  foreground: '#e3e9ec',
  cursor: '#2fb59a',
  cursorAccent: '#0b1416',
  selectionBackground: '#2a78d655',
  black: '#1b2528',
  brightBlack: '#5c6b70',
  red: '#e66767',
  brightRed: '#f08a8a',
  green: '#2fb59a',
  brightGreen: '#5fd3b8',
  yellow: '#eda100',
  brightYellow: '#fab219',
  blue: '#3987e5',
  brightBlue: '#6da7ec',
  magenta: '#d55181',
  brightMagenta: '#e87ba4',
  cyan: '#1baf9f',
  brightCyan: '#5fd3c8',
  white: '#c3cdd1',
  brightWhite: '#ffffff',
}

const RECONNECT_MS = 2000

interface TerminalViewProps {
  sessionId: string
  active: boolean
}

/**
 * One xterm.js terminal attached to a server-side PTY session. Reconnects after
 * a dropped socket; the server replays recent output on every attach, so the
 * screen is reset first.
 */
export function TerminalView({ sessionId, active }: TerminalViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const term = new Terminal({
      theme: THEME,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
      fontSize: 13,
      cursorBlink: true,
      scrollback: 10000,
      allowProposedApi: false,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon((_event, uri) => window.open(uri, '_blank', 'noopener')))
    term.open(container)
    termRef.current = term
    fitRef.current = fit

    let disposed = false
    let exited = false
    let retry: ReturnType<typeof setTimeout> | undefined

    const send = (message: object) => {
      const socket = socketRef.current
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
    }

    const connect = () => {
      const socket = new WebSocket(terminalSocketUrl(sessionId))
      socket.binaryType = 'arraybuffer'
      socketRef.current = socket
      socket.onopen = () => {
        term.reset() // the server replays the recent output
        send({ type: 'resize', cols: term.cols, rows: term.rows })
      }
      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          term.write(new Uint8Array(event.data))
          return
        }
        const message = JSON.parse(event.data as string) as { type: string; code?: number | null }
        if (message.type === 'exit') {
          exited = true
          term.write(`\r\n\x1b[2m[process exited with code ${message.code ?? '?'}]\x1b[0m\r\n`)
        }
      }
      socket.onclose = (event) => {
        if (disposed || exited) return
        if (event.code === 1008) {
          term.write(`\r\n\x1b[31m${event.reason || 'Terminal refused.'}\x1b[0m\r\n`)
          return
        }
        term.write('\r\n\x1b[2m[disconnected, reconnecting…]\x1b[0m')
        retry = setTimeout(connect, RECONNECT_MS)
      }
    }

    const input = term.onData((data) => send({ type: 'input', data }))
    const resize = term.onResize(({ cols, rows }) => send({ type: 'resize', cols, rows }))
    const observer = new ResizeObserver(() => {
      if (container.offsetParent !== null) fit.fit()
    })
    observer.observe(container)
    if (container.offsetParent !== null) fit.fit()
    connect()

    return () => {
      disposed = true
      clearTimeout(retry)
      observer.disconnect()
      input.dispose()
      resize.dispose()
      socketRef.current?.close()
      term.dispose()
    }
  }, [sessionId])

  useEffect(() => {
    if (!active) return
    // The tab was hidden (display: none) while its size may have changed
    requestAnimationFrame(() => {
      fitRef.current?.fit()
      termRef.current?.focus()
    })
  }, [active])

  return <div ref={containerRef} className="h-full w-full px-2 pt-1" />
}
