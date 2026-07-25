import { useEffect } from 'react'
import type { RefObject } from 'react'
import type { RemoteDesktopHandle } from './RemoteDesktopCanvas'
import {
  InputMsgType,
  buildInputFrame,
  encodeKeyEvent,
  encodeMouseButton,
  encodeMouseMove,
  encodeMouseScroll,
} from './protocol'

/**
 * Browser `KeyboardEvent.code` → AT Set 1 (XT) scan codes, as SPICE expects.
 * Extended keys (0xE0xx) are packed into a single number (high byte 0xE0).
 * Inlined so the viewer stays self-contained (no VirtualSpice import).
 */
const SCANCODE_TABLE: Record<string, number> = {
  KeyA: 0x1e, KeyB: 0x30, KeyC: 0x2e, KeyD: 0x20, KeyE: 0x12, KeyF: 0x21,
  KeyG: 0x22, KeyH: 0x23, KeyI: 0x17, KeyJ: 0x24, KeyK: 0x25, KeyL: 0x26,
  KeyM: 0x32, KeyN: 0x31, KeyO: 0x18, KeyP: 0x19, KeyQ: 0x10, KeyR: 0x13,
  KeyS: 0x1f, KeyT: 0x14, KeyU: 0x16, KeyV: 0x2f, KeyW: 0x11, KeyX: 0x2d,
  KeyY: 0x15, KeyZ: 0x2c,
  Digit1: 0x02, Digit2: 0x03, Digit3: 0x04, Digit4: 0x05, Digit5: 0x06,
  Digit6: 0x07, Digit7: 0x08, Digit8: 0x09, Digit9: 0x0a, Digit0: 0x0b,
  F1: 0x3b, F2: 0x3c, F3: 0x3d, F4: 0x3e, F5: 0x3f, F6: 0x40, F7: 0x41,
  F8: 0x42, F9: 0x43, F10: 0x44, F11: 0x57, F12: 0x58,
  ShiftLeft: 0x2a, ShiftRight: 0x36, ControlLeft: 0x1d, ControlRight: 0xe01d,
  AltLeft: 0x38, AltRight: 0xe038, MetaLeft: 0xe05b, MetaRight: 0xe05c,
  ArrowUp: 0xe048, ArrowDown: 0xe050, ArrowLeft: 0xe04b, ArrowRight: 0xe04d,
  Home: 0xe047, End: 0xe04f, PageUp: 0xe049, PageDown: 0xe051,
  Insert: 0xe052, Delete: 0xe053,
  Backspace: 0x0e, Tab: 0x0f, Enter: 0x1c, Escape: 0x01, Space: 0x39,
  CapsLock: 0x3a, NumLock: 0x45, ScrollLock: 0x46,
  Minus: 0x0c, Equal: 0x0d, BracketLeft: 0x1a, BracketRight: 0x1b,
  Backslash: 0x2b, Semicolon: 0x27, Quote: 0x28, Backquote: 0x29,
  Comma: 0x33, Period: 0x34, Slash: 0x35,
  Numpad0: 0x52, Numpad1: 0x4f, Numpad2: 0x50, Numpad3: 0x51, Numpad4: 0x4b,
  Numpad5: 0x4c, Numpad6: 0x4d, Numpad7: 0x47, Numpad8: 0x48, Numpad9: 0x49,
  NumpadDecimal: 0x53, NumpadEnter: 0xe01c, NumpadAdd: 0x4e,
  NumpadSubtract: 0x4a, NumpadMultiply: 0x37, NumpadDivide: 0xe035,
  PrintScreen: 0xe037, Pause: 0xe11d, ContextMenu: 0xe05d,
}

export interface VmSurface {
  width: number
  height: number
}

interface UseVmInputOptions {
  canvasRef: RefObject<RemoteDesktopHandle | null>
  send: (buf: ArrayBuffer) => void
  surface: VmSurface | null
  viewOnly: boolean
}

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

/**
 * Attaches keyboard / mouse / wheel listeners to the viewer canvas and streams
 * SPICE Input-channel frames on the shared display socket. Absolute-mouse
 * coordinates are mapped through the same scale-to-fit (object-contain) math
 * the canvas uses to display the guest surface. No-op while `viewOnly`.
 */
export function useVmInput({ canvasRef, send, surface, viewOnly }: UseVmInputOptions): void {
  useEffect(() => {
    if (viewOnly || !surface) return
    const canvas = canvasRef.current?.getCanvas()
    if (!canvas) return

    canvas.tabIndex = 0
    canvas.style.outline = 'none'

    // --- Absolute-mouse coordinate mapping (client → guest surface) ---
    const toGuestCoords = (clientX: number, clientY: number): { x: number; y: number } => {
      const rect = canvas.getBoundingClientRect()
      const { width: sw, height: sh } = surface
      // object-contain: the surface is scaled uniformly and centered (letterboxed).
      const scale = Math.min(rect.width / sw, rect.height / sh) || 1
      const dispW = sw * scale
      const dispH = sh * scale
      const offX = (rect.width - dispW) / 2
      const offY = (rect.height - dispH) / 2
      const localX = clientX - rect.left - offX
      const localY = clientY - rect.top - offY
      return {
        x: clamp(Math.round(localX / scale), 0, sw - 1),
        y: clamp(Math.round(localY / scale), 0, sh - 1),
      }
    }

    // --- Mouse move: coalesce to one send per animation frame ---
    let pendingMove: { x: number; y: number } | null = null
    let moveRaf = 0
    const flushMove = () => {
      moveRaf = 0
      if (!pendingMove) return
      send(buildInputFrame(InputMsgType.MouseMove, encodeMouseMove(pendingMove)))
      pendingMove = null
    }
    const handlePointerMove = (e: PointerEvent) => {
      pendingMove = toGuestCoords(e.clientX, e.clientY)
      if (moveRaf === 0) moveRaf = requestAnimationFrame(flushMove)
    }

    const handlePointerDown = (e: PointerEvent) => {
      canvas.focus()
      try {
        canvas.setPointerCapture(e.pointerId)
      } catch {
        // Pointer may already be released; capture is best-effort.
      }
      // Send the position first so the button lands where the cursor is.
      const pos = toGuestCoords(e.clientX, e.clientY)
      send(buildInputFrame(InputMsgType.MouseMove, encodeMouseMove(pos)))
      send(buildInputFrame(InputMsgType.MouseButton, encodeMouseButton({ button: e.button, pressed: true })))
    }

    const handlePointerUp = (e: PointerEvent) => {
      try {
        canvas.releasePointerCapture(e.pointerId)
      } catch {
        // Ignore if not captured.
      }
      send(buildInputFrame(InputMsgType.MouseButton, encodeMouseButton({ button: e.button, pressed: false })))
    }

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      send(
        buildInputFrame(
          InputMsgType.MouseScroll,
          encodeMouseScroll({ dx: Math.round(e.deltaX), dy: Math.round(e.deltaY) }),
        ),
      )
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      const scancode = SCANCODE_TABLE[e.code]
      if (scancode === undefined) return
      e.preventDefault()
      send(buildInputFrame(InputMsgType.KeyDown, encodeKeyEvent({ scancode })))
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      const scancode = SCANCODE_TABLE[e.code]
      if (scancode === undefined) return
      e.preventDefault()
      send(buildInputFrame(InputMsgType.KeyUp, encodeKeyEvent({ scancode })))
    }

    const handleContextMenu = (e: MouseEvent) => e.preventDefault()

    canvas.addEventListener('pointermove', handlePointerMove)
    canvas.addEventListener('pointerdown', handlePointerDown)
    canvas.addEventListener('pointerup', handlePointerUp)
    canvas.addEventListener('wheel', handleWheel, { passive: false })
    canvas.addEventListener('keydown', handleKeyDown)
    canvas.addEventListener('keyup', handleKeyUp)
    canvas.addEventListener('contextmenu', handleContextMenu)

    return () => {
      if (moveRaf !== 0) cancelAnimationFrame(moveRaf)
      canvas.removeEventListener('pointermove', handlePointerMove)
      canvas.removeEventListener('pointerdown', handlePointerDown)
      canvas.removeEventListener('pointerup', handlePointerUp)
      canvas.removeEventListener('wheel', handleWheel)
      canvas.removeEventListener('keydown', handleKeyDown)
      canvas.removeEventListener('keyup', handleKeyUp)
      canvas.removeEventListener('contextmenu', handleContextMenu)
    }
  }, [canvasRef, send, surface, viewOnly])
}
