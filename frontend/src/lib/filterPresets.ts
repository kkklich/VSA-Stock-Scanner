// Saved screen presets for the Filters page — a named combination of filter
// values the user can re-run with one click. Persisted in localStorage (same
// approach as favorites) so presets survive reloads on this browser.

import type { SignalVerdict } from '../types'

export const FILTER_PRESETS_KEY = 'stockpilot:filter-presets'

/**
 * Where the stock sits in its 52-week range. One control instead of four
 * separate inputs, because the useful screens are a small fixed set:
 * breakouts ("new high"), stocks pressing against the high ("near high"),
 * breakdowns and stocks scraping the low.
 */
export type Range52w = 'any' | 'newHigh' | 'nearHigh' | 'newLow' | 'nearLow'

/** How close to the extreme "near high"/"near low" means, in percent. */
export const NEAR_52W_PCT = 5

/** The filter values a preset captures (everything on the Filters page). */
export interface ScreenFilters {
  /** Free-text search over ticker + name. */
  q: string
  /** Exact sector name, or 'all'. */
  sector: string
  /** VSA rating band, 0–100 inclusive. */
  minRating: number
  maxRating: number
  /** Signal verdict, or 'all'. */
  signal: SignalVerdict | 'all'
  /** Last signal at most this many sessions ago; null = any age. */
  maxDaysSinceSignal: number | null
  /** Price range in PLN; null = unbounded. */
  minPrice: number | null
  maxPrice: number | null
  /** Minimum 20-session median volume (shares); null = any. */
  minVolume: number | null
  /** Position in the 52-week range; 'any' = no filter. */
  range52w: Range52w
  /**
   * Only stocks whose weekly VSA verdict confirms the daily one (both lean
   * the same way) — the higher-timeframe agreement VSA traders look for.
   */
  weeklyConfirms: boolean
}

export interface FilterPreset {
  /** Unique id (timestamp-based) so renames/duplicate names are harmless. */
  id: string
  name: string
  /** ISO datetime the preset was saved. */
  createdAt: string
  filters: ScreenFilters
}

export const EMPTY_FILTERS: ScreenFilters = {
  q: '',
  sector: 'all',
  minRating: 0,
  maxRating: 100,
  signal: 'all',
  maxDaysSinceSignal: null,
  minPrice: null,
  maxPrice: null,
  minVolume: null,
  range52w: 'any',
  weeklyConfirms: false,
}

/** Read the persisted presets (safe if localStorage is unavailable). */
export function loadPresets(): FilterPreset[] {
  try {
    const raw = localStorage.getItem(FILTER_PRESETS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as FilterPreset[]
    if (!Array.isArray(parsed)) return []
    // Merge with EMPTY_FILTERS so presets saved by an older version of the
    // page never leave a newer filter field undefined.
    return parsed.map((p) => ({
      ...p,
      filters: { ...EMPTY_FILTERS, ...p.filters },
    }))
  } catch {
    return []
  }
}

/** Persist the presets list (ignores quota / private-mode errors). */
export function savePresets(presets: FilterPreset[]): void {
  try {
    localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(presets))
  } catch {
    /* ignore */
  }
}

/** Build a new preset from the current filter values. */
export function createPreset(name: string, filters: ScreenFilters): FilterPreset {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: name.trim(),
    createdAt: new Date().toISOString(),
    filters: { ...filters },
  }
}

/** True when any filter differs from its "no filter" default. */
export function filtersActive(f: ScreenFilters): boolean {
  return (
    f.q.trim() !== '' ||
    f.sector !== 'all' ||
    f.minRating > 0 ||
    f.maxRating < 100 ||
    f.signal !== 'all' ||
    f.maxDaysSinceSignal !== null ||
    f.minPrice !== null ||
    f.maxPrice !== null ||
    f.minVolume !== null ||
    f.range52w !== 'any' ||
    f.weeklyConfirms
  )
}

/** Translate the 52-week selection into the ranking endpoint's parameters. */
export function range52wParams(range: Range52w): {
  maxDistFrom52wHighPct?: number
  maxDistFrom52wLowPct?: number
  new52wHigh?: boolean
  new52wLow?: boolean
} {
  switch (range) {
    case 'newHigh':
      return { new52wHigh: true }
    case 'nearHigh':
      return { maxDistFrom52wHighPct: NEAR_52W_PCT }
    case 'newLow':
      return { new52wLow: true }
    case 'nearLow':
      return { maxDistFrom52wLowPct: NEAR_52W_PCT }
    default:
      return {}
  }
}
