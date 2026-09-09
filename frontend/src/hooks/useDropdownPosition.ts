// Keeps a toolbar dropdown panel on screen.
//
// The panels in this app used to hang off their button with `absolute right-0`,
// lining the panel's right edge up with the button's. That reads well on a wide
// screen, where the toolbar sits over on the right — but on a phone the toolbar
// wraps to the left edge, and a 320px panel anchored to a button only 79px from
// that edge was drawn almost entirely off-screen (measured: left = -241px on a
// 375px viewport). Measuring the button and clamping to the viewport keeps the
// desktop placement pixel-identical while making the panel reachable on a phone.

import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'

/** Space between the button and the panel. */
const GAP = 8
/** Smallest gap left between the panel and the edge of the screen. */
const MARGIN = 16
/** Never squash the panel below this, even on a very short viewport. */
const MIN_HEIGHT = 160

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(Math.max(value, lo), hi)
}

/**
 * Fixed viewport coordinates for a panel `preferredWidth` wide hanging under
 * `button`. Keeps the right-aligned placement when it fits, then clamps both
 * edges inside the viewport; `maxHeight` stops a long list running off the
 * bottom of a short screen (the panel scrolls instead).
 */
export function dropdownPosition(
  button: DOMRect,
  preferredWidth: number,
  viewport: { width: number; height: number },
): CSSProperties {
  const width = Math.min(preferredWidth, Math.max(0, viewport.width - MARGIN * 2))
  const left = clamp(
    button.right - width,
    MARGIN,
    Math.max(MARGIN, viewport.width - width - MARGIN),
  )
  const top = button.bottom + GAP
  return {
    position: 'fixed',
    top,
    left,
    width,
    maxHeight: Math.max(MIN_HEIGHT, viewport.height - top - MARGIN),
  }
}

/**
 * Positions an open dropdown panel under its trigger button. Re-measures on
 * scroll and resize so the panel tracks the button the way an `absolute` one
 * would — the page's scroll container is the inner `<main>`, not the window,
 * hence the capture-phase scroll listener.
 *
 * `style` is `null` until the button has been measured; render the panel only
 * once it is set, so an unpositioned panel never lands in the toolbar's flow
 * and shifts the very button we are measuring.
 */
export function useDropdownPosition(open: boolean, preferredWidth: number) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [style, setStyle] = useState<CSSProperties | null>(null)

  const measure = useCallback(() => {
    const el = buttonRef.current
    if (!el) return
    setStyle(
      dropdownPosition(el.getBoundingClientRect(), preferredWidth, {
        width: window.innerWidth,
        height: window.innerHeight,
      }),
    )
  }, [preferredWidth])

  useLayoutEffect(() => {
    if (!open) {
      setStyle(null)
      return
    }
    measure()
    window.addEventListener('scroll', measure, true)
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('scroll', measure, true)
      window.removeEventListener('resize', measure)
    }
  }, [open, measure])

  return { buttonRef, style }
}
