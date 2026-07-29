// Display Web Worker: receives WS binary frames, decodes images, and renders
// them to an OffscreenCanvas — fully isolated from the React main thread so no
// reconciliation can stall a frame.
//
// Pacing: incoming draws are decoded in arrival order and queued; the canvas is
// painted at most once per animation frame (a dirty queue drained on rAF, with
// a setTimeout fallback for worker scopes that lack requestAnimationFrame).

import {
  decodeFrame,
  decodeSurfaceCreate,
  decodeSurfaceDestroy,
  decodeDrawFrame,
  decodeDrawFrameRaw,
  ChannelTag,
  DisplayMsgType,
} from './protocol'

let canvas: OffscreenCanvas | null = null
let ctx: OffscreenCanvasRenderingContext2D | null = null

// Track current surface dimensions for resize handling.
let currentWidth = 0
let currentHeight = 0

interface PendingDraw {
  bitmap: ImageBitmap
  x: number
  y: number
}

// Draws decoded and awaiting paint, in strict arrival order.
const pendingDraws: PendingDraw[] = []
// Serializes async image decoding so bitmaps enqueue in frame-arrival order.
let decodeChain: Promise<void> = Promise.resolve()
let flushScheduled = false

const scheduleFlush = (() => {
  const raf: typeof requestAnimationFrame | undefined =
    typeof requestAnimationFrame === 'function' ? requestAnimationFrame : undefined
  return () => {
    if (flushScheduled) return
    flushScheduled = true
    if (raf) {
      raf(flush)
    } else {
      setTimeout(flush, 16)
    }
  }
})()

function flush(): void {
  flushScheduled = false
  if (!ctx) {
    // Context vanished; drop queued bitmaps to avoid a leak.
    for (const d of pendingDraws) d.bitmap.close()
    pendingDraws.length = 0
    return
  }
  // Drain everything queued this frame in one paint pass.
  for (let i = 0; i < pendingDraws.length; i++) {
    const d = pendingDraws[i]
    ctx.drawImage(d.bitmap, d.x, d.y)
    d.bitmap.close()
  }
  pendingDraws.length = 0
}

function enqueueDraw(bitmap: ImageBitmap, x: number, y: number): void {
  pendingDraws.push({ bitmap, x, y })
  scheduleFlush()
}

type WorkerMessage =
  | { type: 'init'; canvas: OffscreenCanvas }
  | { type: 'resize'; width: number; height: number }
  | { type: 'frame'; data: ArrayBuffer }

self.onmessage = (e: MessageEvent<WorkerMessage>) => {
  const msg = e.data

  switch (msg.type) {
    case 'init': {
      canvas = msg.canvas
      ctx = canvas.getContext('2d')
      if (!ctx) {
        console.error('Failed to get 2d context from OffscreenCanvas')
      }
      break
    }

    case 'resize': {
      if (canvas && msg.width > 0 && msg.height > 0) {
        canvas.width = msg.width
        canvas.height = msg.height
        currentWidth = msg.width
        currentHeight = msg.height
      }
      break
    }

    case 'frame': {
      handleFrame(msg.data)
      break
    }
  }
}

function handleFrame(data: ArrayBuffer): void {
  if (!ctx || !canvas) return

  const frame = decodeFrame(data)
  if (frame.channel !== ChannelTag.Display) return

  switch (frame.msgType) {
    case DisplayMsgType.SurfaceCreate: {
      const surface = decodeSurfaceCreate(frame.payload)
      // Resize for the primary surface (id=0) or the very first surface seen.
      if (surface.surfaceId === 0 || (currentWidth === 0 && currentHeight === 0)) {
        canvas.width = surface.width
        canvas.height = surface.height
        currentWidth = surface.width
        currentHeight = surface.height
      }
      self.postMessage({
        type: 'surfaceCreate',
        surfaceId: surface.surfaceId,
        width: surface.width,
        height: surface.height,
      })
      break
    }

    case DisplayMsgType.SurfaceDestroy: {
      const destroy = decodeSurfaceDestroy(frame.payload)
      self.postMessage({ type: 'surfaceDestroy', surfaceId: destroy.surfaceId })
      break
    }

    case DisplayMsgType.DrawFrame: {
      const draw = decodeDrawFrame(frame.payload)
      // Copy out of the transferred buffer before async decode.
      const png = draw.pngData.slice()
      decodeChain = decodeChain.then(async () => {
        const blob = new Blob([png], { type: 'image/png' })
        const bitmap = await createImageBitmap(blob)
        enqueueDraw(bitmap, draw.x, draw.y)
      })
      break
    }

    case DisplayMsgType.DrawFrameRaw: {
      const draw = decodeDrawFrameRaw(frame.payload)
      const rgba = new Uint8ClampedArray(draw.rgbaData)
      const imageData = new ImageData(rgba, draw.width, draw.height)
      decodeChain = decodeChain.then(async () => {
        const bitmap = await createImageBitmap(imageData)
        enqueueDraw(bitmap, draw.x, draw.y)
      })
      break
    }
  }
}
