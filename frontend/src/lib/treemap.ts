import type { ChartPalette } from './chartTheme'

function mix(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): string {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

/** Diverging rose → neutral → emerald color for t in [-1, +1]. */
export function heatmapColor(t: number, palette: ChartPalette): string {
  const clamped = Math.max(-1, Math.min(1, t))
  return clamped < 0
    ? mix(palette.heatmapNeutral, palette.heatmapNegative, -clamped)
    : mix(palette.heatmapNeutral, palette.heatmapPositive, clamped)
}

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

/**
 * Squarified treemap (Bruls et al.): splits `rect` into one sub-rectangle per
 * value, areas proportional to the values, keeping tiles close to square.
 * Values must be positive and sorted descending for best results.
 */
export function squarify(values: number[], rect: Rect): Rect[] {
  const rects: Rect[] = values.map(() => ({ x: rect.x, y: rect.y, w: 0, h: 0 }))
  const total = values.reduce((a, b) => a + b, 0)
  if (total <= 0 || rect.w <= 0 || rect.h <= 0) return rects

  // Scale values so they sum to the rectangle's area.
  const areas = values.map((v) => (v / total) * rect.w * rect.h)

  let { x, y, w, h } = rect
  let start = 0
  while (start < areas.length) {
    // Lay the next row along the shorter edge; greedily grow it while the
    // worst tile aspect ratio keeps improving.
    const horizontal = w >= h // row is a vertical strip on the left
    const side = horizontal ? h : w
    let end = start
    let sum = 0
    let best = Infinity
    while (end < areas.length) {
      const trySum = sum + areas[end]
      const thickness = trySum / side
      let worst = 0
      for (let i = start; i <= end; i++) {
        const len = areas[i] / thickness
        worst = Math.max(worst, thickness / len, len / thickness)
      }
      if (worst <= best) {
        best = worst
        sum = trySum
        end++
      } else {
        break
      }
    }

    const thickness = sum / side
    let offset = 0
    for (let i = start; i < end; i++) {
      const len = areas[i] / thickness
      rects[i] = horizontal
        ? { x, y: y + offset, w: thickness, h: len }
        : { x: x + offset, y, w: len, h: thickness }
      offset += len
    }
    if (horizontal) {
      x += thickness
      w -= thickness
    } else {
      y += thickness
      h -= thickness
    }
    start = end
  }
  return rects
}
