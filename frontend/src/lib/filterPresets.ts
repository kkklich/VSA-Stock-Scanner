// Saved screen presets for the Filters page — a named combination of filter
// values the user can re-run with one click. Persisted in localStorage (same
// approach as favorites) so presets survive reloads on this browser.

import type { SignalVerdict } from '../types'

export const FILTER_PRESETS_KEY = 'stockpilot:filter-presets'

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
    f.minVolume !== null
  )
}
