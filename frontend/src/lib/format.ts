// Small formatting + color helpers shared across the UI.

/** Format a number as a price with two decimals. */
export const fmtPrice = (n: number): string =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Signed percent, e.g. +1.12% / -0.62%. */
export const fmtPct = (n: number): string => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`

/** Signed integer, e.g. +2 / -1. */
export const fmtSigned = (n: number): string => `${n >= 0 ? '+' : ''}${n}`

/**
 * VSA rating badge color band (per DOCUMENTATION.md §4):
 *  > 70 green, < 30 red, otherwise neutral slate.
 */
export function ratingTone(rating: number): {
  text: string
  bar: string
  badge: string
} {
  if (rating > 70)
    return {
      text: 'text-emerald-400',
      bar: 'bg-emerald-500',
      badge: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
    }
  if (rating < 30)
    return {
      text: 'text-rose-400',
      bar: 'bg-rose-500',
      badge: 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
    }
  return {
    text: 'text-slate-300',
    bar: 'bg-slate-400',
    badge: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
  }
}

/** Directional text color for a numeric delta. */
export const deltaTone = (n: number): string =>
  n > 0 ? 'text-emerald-400' : n < 0 ? 'text-rose-400' : 'text-slate-400'
