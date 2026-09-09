import { describe, expect, it } from 'vitest'
import { dropdownPosition } from './useDropdownPosition'

/** A button's measured box; only the edges the helper reads matter. */
function rect(left: number, right: number, bottom = 100): DOMRect {
  return { left, right, bottom, top: bottom - 36, width: right - left, height: 36 } as DOMRect
}

const DESKTOP = { width: 1440, height: 900 }
const PHONE = { width: 375, height: 812 }

describe('dropdownPosition', () => {
  it('keeps the right-aligned desktop placement when the panel fits', () => {
    const button = rect(1115, 1233)
    const s = dropdownPosition(button, 320, DESKTOP)

    // Same look as the old `absolute right-0`: panel's right edge on the
    // button's right edge, full width, 8px below.
    expect(s.width).toBe(320)
    expect(Number(s.left) + 320).toBe(button.right)
    expect(s.top).toBe(button.bottom + 8)
    expect(s.position).toBe('fixed')
  })

  it('pulls the panel back on screen when the button sits near the left edge', () => {
    // The reported bug: on a phone the toolbar wraps left, and right-aligning
    // a 320px panel to a button 79px in put its left edge at -241px.
    const button = rect(16, 79)
    expect(button.right - 320).toBeLessThan(0)

    const s = dropdownPosition(button, 320, PHONE)
    expect(s.left).toBe(16)
    expect(Number(s.left) + Number(s.width)).toBeLessThanOrEqual(PHONE.width)
  })

  it('keeps the panel on screen when the button sits near the right edge', () => {
    const s = dropdownPosition(rect(320, 366), 320, PHONE)
    expect(Number(s.left)).toBeGreaterThanOrEqual(16)
    expect(Number(s.left) + Number(s.width)).toBeLessThanOrEqual(PHONE.width - 16)
  })

  it('narrows a panel wider than the screen instead of overflowing it', () => {
    const s = dropdownPosition(rect(16, 79), 320, { width: 320, height: 640 })
    expect(s.width).toBe(320 - 32)
    expect(s.left).toBe(16)
  })

  it('caps the height to the room below the button so a long list scrolls', () => {
    const s = dropdownPosition(rect(16, 79, 600), 320, PHONE)
    expect(s.maxHeight).toBe(812 - 608 - 16)
  })

  it('never squashes the panel to nothing on a short viewport', () => {
    const s = dropdownPosition(rect(16, 79, 380), 320, { width: 375, height: 400 })
    expect(Number(s.maxHeight)).toBeGreaterThanOrEqual(160)
  })
})
