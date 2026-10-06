let ctx: CanvasRenderingContext2D | null | undefined

/** Pixel width of a label, so label columns fit their longest text instead of clipping. */
export function textWidth(text: string, font = '12px system-ui, -apple-system, sans-serif'): number {
  if (ctx === undefined) {
    try {
      ctx = document.createElement('canvas').getContext('2d')
    } catch {
      ctx = null
    }
  }
  if (!ctx) return text.length * 6.8 // jsdom / no canvas: rough average glyph width
  ctx.font = font
  return ctx.measureText(text).width
}
