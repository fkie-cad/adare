/**
 * WebSocket service for real-time updates
 * Handles connection, reconnection, and event subscriptions
 */

import type { WebSocketMessage, WebSocketMessageType } from '@/types/api'

type MessageHandler = (message: WebSocketMessage) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private sessionId: string
  private url: string
  private reconnectInterval: number = 3000
  private reconnectTimer: number | null = null
  private pingInterval: number = 30000
  private pingTimer: number | null = null
  private handlers: Map<WebSocketMessageType, Set<MessageHandler>> = new Map()
  private isManualClose: boolean = false

  constructor(sessionId: string) {
    this.sessionId = sessionId
    // Use WS protocol for WebSocket, auto-detect host
    // Connect to the same origin so the Vite dev proxy (see vite.config.ts,
    // which forwards `/ws` to the backend) and production both work without a
    // hardcoded port.
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.url = `${protocol}//${window.location.host}/ws/${sessionId}`
  }

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    this.isManualClose = false
    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      this.startPingInterval()
      this.emit('connected', {})
    }

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data)
        this.handleMessage(message)
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      this.emit('error', { error: 'WebSocket connection error' })
    }

    this.ws.onclose = () => {
      this.stopPingInterval()
      this.emit('disconnected', {})

      // Auto-reconnect unless manually closed
      if (!this.isManualClose) {
        this.scheduleReconnect()
      }
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.isManualClose = true
    this.stopPingInterval()
    this.stopReconnectTimer()

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  /**
   * Subscribe to a message type
   */
  on(type: WebSocketMessageType | 'connected' | 'disconnected', handler: MessageHandler): void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set())
    }
    this.handlers.get(type)!.add(handler)
  }

  /**
   * Unsubscribe from a message type
   */
  off(type: WebSocketMessageType | 'connected' | 'disconnected', handler: MessageHandler): void {
    const handlers = this.handlers.get(type)
    if (handlers) {
      handlers.delete(handler)
    }
  }

  /**
   * Send a message to the server
   */
  send(message: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket not connected, cannot send message')
    }
  }

  /**
   * Handle incoming message
   */
  private handleMessage(message: WebSocketMessage): void {
    const handlers = this.handlers.get(message.type)
    if (handlers) {
      handlers.forEach((handler) => handler(message))
    }
  }

  /**
   * Emit event to all subscribers
   */
  private emit(type: WebSocketMessageType | 'connected' | 'disconnected', data: any): void {
    const message: WebSocketMessage = {
      type: type as WebSocketMessageType,
      session_id: this.sessionId,
      data,
      timestamp: new Date().toISOString(),
    }
    this.handleMessage(message)
  }

  /**
   * Start ping interval to keep connection alive
   */
  private startPingInterval(): void {
    this.stopPingInterval()
    this.pingTimer = window.setInterval(() => {
      this.send({ type: 'ping', session_id: this.sessionId })
    }, this.pingInterval)
  }

  /**
   * Stop ping interval
   */
  private stopPingInterval(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }

  /**
   * Schedule reconnection attempt
   */
  private scheduleReconnect(): void {
    this.stopReconnectTimer()
    this.reconnectTimer = window.setTimeout(() => {
      this.connect()
    }, this.reconnectInterval)
  }

  /**
   * Stop reconnection timer
   */
  private stopReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  /**
   * Get connection state
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

/**
 * WebSocket manager for multiple sessions
 */
class WebSocketManager {
  private clients: Map<string, WebSocketClient> = new Map()

  /**
   * Get or create WebSocket client for session
   */
  getClient(sessionId: string): WebSocketClient {
    if (!this.clients.has(sessionId)) {
      const client = new WebSocketClient(sessionId)
      this.clients.set(sessionId, client)
    }
    return this.clients.get(sessionId)!
  }

  /**
   * Disconnect and remove client
   */
  removeClient(sessionId: string): void {
    const client = this.clients.get(sessionId)
    if (client) {
      client.disconnect()
      this.clients.delete(sessionId)
    }
  }

  /**
   * Disconnect all clients
   */
  disconnectAll(): void {
    this.clients.forEach((client) => client.disconnect())
    this.clients.clear()
  }
}

// Export singleton instance
export const wsManager = new WebSocketManager()
