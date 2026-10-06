// Plain-language readings of the volume-surge row's bar-level context
// (roadmap #15b). The thresholds are the VSA engine's own, so a bar this calls
// "wide" is wide in the terms the ratings use (backend app/analysis/vsa.py).

import type { ApiVolumeSurgeItem } from '../api/stocksApi'

/** The engine's wide-spread default (SOS / SOW `spread_mult`). */
export const WIDE_SPREAD = 1.5
/** The engine's narrow-spread default (No Demand `spread_mult`). */
export const NARROW_SPREAD = 0.7

export type SpreadClass = 'wide' | 'average' | 'narrow'
export type CloseClass = 'high' | 'middle' | 'low'

/** Wide / average / narrow against the reference period's average spread. */
export function spreadClass(ratio: number | null): SpreadClass | null {
  if (ratio == null) return null
  if (ratio >= WIDE_SPREAD) return 'wide'
  if (ratio <= NARROW_SPREAD) return 'narrow'
  return 'average'
}

/** Where the bar closed, in thirds of its range (the Glinicki course's reading). */
export function closeClass(position: number | null): CloseClass | null {
  if (position == null) return null
  if (position >= 2 / 3) return 'high'
  if (position <= 1 / 3) return 'low'
  return 'middle'
}

/** "Wide, closed high" — the peak session's spread and close in a few words. */
export function describePeakBar(item: ApiVolumeSurgeItem): string {
  const close = closeClass(item.peakClosePosition)
  if (close == null) return 'No price range'
  const spread = spreadClass(item.peakSpreadRatio)
  const parts = [spread, `closed ${close === 'middle' ? 'mid' : close}`].filter(Boolean)
  return capitalise(parts.join(', '))
}

/** The same reading with its numbers, for the tooltip. */
export function peakBarDetail(item: ApiVolumeSurgeItem): string {
  const spread =
    item.peakSpreadRatio == null
      ? 'no reference spread'
      : `spread ${item.peakSpreadRatio.toFixed(1)}× the reference average`
  const close =
    item.peakClosePosition == null
      ? 'no price range'
      : `closed at ${Math.round(item.peakClosePosition * 100)}% of its range`
  const move = `${item.peakChangePct >= 0 ? '+' : ''}${item.peakChangePct.toFixed(2)}% on the day`
  return `Busiest session ${fmtSessionDay(item.peakDate)}: ${item.peakVolumeRatio.toFixed(1)}× a typical day's volume, ${spread}, ${close}, ${move}.`
}

/** "Wed 24.09" — a session in the surge window. */
export function fmtSessionDay(iso: string): string {
  // Noon, so no time zone can move the calendar day.
  const d = new Date(`${iso}T12:00:00`)
  const weekday = d.toLocaleDateString('en-GB', { weekday: 'short' })
  const day = d.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })
  return `${weekday} ${day}`
}

export type SignalAge =
  | { kind: 'none' }
  | { kind: 'inSurge'; days: number }
  | { kind: 'beforeSurge'; days: number }

/**
 * How the row's VSA verdict relates to the surge. The verdict is a decayed
 * score over months of signals, so without this a weeks-old verdict reads as
 * if it described the last three sessions.
 */
export function signalAge(item: ApiVolumeSurgeItem): SignalAge {
  if (item.daysSinceSignal >= 999) return { kind: 'none' }
  return item.signalInWindow
    ? { kind: 'inSurge', days: item.daysSinceSignal }
    : { kind: 'beforeSurge', days: item.daysSinceSignal }
}

/** The short line under the signal badge: "last signal 12 d ago". */
export function signalAgeLabel(item: ApiVolumeSurgeItem): string {
  const age = signalAge(item)
  if (age.kind === 'none') return 'no recent signal'
  return age.kind === 'inSurge' ? 'signal in the surge' : `last signal ${age.days} d ago`
}

/** Its tooltip: "Last signal 12 d ago, before the surge" and friends. */
export function signalAgeText(item: ApiVolumeSurgeItem): string {
  const age = signalAge(item)
  if (age.kind === 'none') return 'No VSA signal in the last 4 months'
  const when = age.days === 0 ? 'on the last session' : `${age.days} d ago`
  return age.kind === 'inSurge'
    ? `Signal ${when}, during the surge`
    : `Last signal ${when}, before the surge`
}

function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
