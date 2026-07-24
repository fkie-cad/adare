// Binary WebSocket frame codec for the ADARE-owned SPICE viewer.
//
// Self-contained port of VirtualSpice's frame protocol (the only channels the
// viewer needs: Display, Cursor, Input). Frame layout, all little-endian:
//   [1B channel][1B msgType][4B payloadLen u32 LE][payload]

// === Channel Tags ===

export const ChannelTag = {
  Display: 0x01,
  Cursor: 0x02,
  Input: 0x03,
} as const
export type ChannelTag = (typeof ChannelTag)[keyof typeof ChannelTag]

// === Display Messages (Channel 0x01, server → client) ===

export const DisplayMsgType = {
  SurfaceCreate: 0x01,
  SurfaceDestroy: 0x02,
  DrawFrame: 0x03,
  DrawFrameRaw: 0x04,
} as const
export type DisplayMsgType = (typeof DisplayMsgType)[keyof typeof DisplayMsgType]

export interface SurfaceCreate {
  surfaceId: number
  width: number
  height: number
  format: number
}

export interface SurfaceDestroy {
  surfaceId: number
}

export interface DrawFrame {
  surfaceId: number
  x: number
  y: number
  width: number
  height: number
  pngData: Uint8Array
}

export interface DrawFrameRaw {
  surfaceId: number
  x: number
  y: number
  width: number
  height: number
  rgbaData: Uint8Array
}

// === Cursor Messages (Channel 0x02, server → client) ===

export const CursorMsgType = {
  Set: 0x01,
  Move: 0x02,
  Hide: 0x03,
} as const
export type CursorMsgType = (typeof CursorMsgType)[keyof typeof CursorMsgType]

export interface CursorSet {
  hotX: number
  hotY: number
  width: number
  height: number
  rgbaData: Uint8Array
}

export interface CursorMove {
  x: number
  y: number
}

// === Input Messages (Channel 0x03, client → server) ===

export const InputMsgType = {
  KeyDown: 0x01,
  KeyUp: 0x02,
  MouseMove: 0x03,
  MouseButton: 0x04,
  MouseScroll: 0x05,
} as const
export type InputMsgType = (typeof InputMsgType)[keyof typeof InputMsgType]

export interface KeyEvent {
  scancode: number
}

export interface MouseMoveEvent {
  x: number
  y: number
}

export interface MouseButtonEvent {
  button: number
  pressed: boolean
}

export interface MouseScrollEvent {
  dx: number
  dy: number
}

// === Frame Encode/Decode ===

export const FRAME_HEADER_SIZE = 6

export interface WsFrame {
  channel: number
  msgType: number
  payload: Uint8Array
}

export function encodeFrame(frame: WsFrame): ArrayBuffer {
  const buf = new ArrayBuffer(FRAME_HEADER_SIZE + frame.payload.byteLength)
  const view = new DataView(buf)
  view.setUint8(0, frame.channel)
  view.setUint8(1, frame.msgType)
  view.setUint32(2, frame.payload.byteLength, true)
  new Uint8Array(buf, FRAME_HEADER_SIZE).set(frame.payload)
  return buf
}

export function decodeFrame(data: ArrayBuffer): WsFrame {
  if (data.byteLength < FRAME_HEADER_SIZE) {
    throw new Error('Frame too short')
  }
  const view = new DataView(data)
  const channel = view.getUint8(0)
  const msgType = view.getUint8(1)
  const payloadLen = view.getUint32(2, true)
  if (data.byteLength < FRAME_HEADER_SIZE + payloadLen) {
    throw new Error('Frame payload truncated')
  }
  const payload = new Uint8Array(data, FRAME_HEADER_SIZE, payloadLen)
  return { channel, msgType, payload }
}

// === Display Payload Decoders (server → client) ===

export function decodeSurfaceCreate(data: Uint8Array): SurfaceCreate {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  return {
    surfaceId: view.getUint32(0, true),
    width: view.getUint32(4, true),
    height: view.getUint32(8, true),
    format: view.getUint32(12, true),
  }
}

export function decodeSurfaceDestroy(data: Uint8Array): SurfaceDestroy {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  return { surfaceId: view.getUint32(0, true) }
}

export function decodeDrawFrame(data: Uint8Array): DrawFrame {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  return {
    surfaceId: view.getUint32(0, true),
    x: view.getUint32(4, true),
    y: view.getUint32(8, true),
    width: view.getUint32(12, true),
    height: view.getUint32(16, true),
    pngData: data.slice(20),
  }
}

export function decodeDrawFrameRaw(data: Uint8Array): DrawFrameRaw {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  return {
    surfaceId: view.getUint32(0, true),
    x: view.getUint32(4, true),
    y: view.getUint32(8, true),
    width: view.getUint32(12, true),
    height: view.getUint32(16, true),
    rgbaData: data.slice(20),
  }
}

// === Cursor Payload Decoders (server → client) ===

export function decodeCursorSet(data: Uint8Array): CursorSet {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  return {
    hotX: view.getUint16(0, true),
    hotY: view.getUint16(2, true),
    width: view.getUint16(4, true),
    height: view.getUint16(6, true),
    rgbaData: data.slice(8),
  }
}

export function decodeCursorMove(data: Uint8Array): CursorMove {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength)
  return {
    x: view.getUint32(0, true),
    y: view.getUint32(4, true),
  }
}

// === Input Payload Encoders (client → server) ===

export function encodeKeyEvent(event: KeyEvent): Uint8Array {
  const buf = new ArrayBuffer(4)
  new DataView(buf).setUint32(0, event.scancode, true)
  return new Uint8Array(buf)
}

export function encodeMouseMove(event: MouseMoveEvent): Uint8Array {
  const buf = new ArrayBuffer(8)
  const view = new DataView(buf)
  view.setUint32(0, event.x, true)
  view.setUint32(4, event.y, true)
  return new Uint8Array(buf)
}

export function encodeMouseButton(event: MouseButtonEvent): Uint8Array {
  return new Uint8Array([event.button, event.pressed ? 1 : 0])
}

export function encodeMouseScroll(event: MouseScrollEvent): Uint8Array {
  const buf = new ArrayBuffer(8)
  const view = new DataView(buf)
  view.setInt32(0, event.dx, true)
  view.setInt32(4, event.dy, true)
  return new Uint8Array(buf)
}

// === Convenience: build a full Input-channel WS frame ===

export function buildInputFrame(msgType: number, payload: Uint8Array): ArrayBuffer {
  return encodeFrame({ channel: ChannelTag.Input, msgType, payload })
}
