import { MAX_SORT_LEVELS, serializeSort, type SortLevel } from './sorting'
import type { UrlField } from '../hooks/useUrlState'

export const RANKING_SORT_KEYS = [
  'ticker', 'name', 'lastPrice', 'priceChangePct', 'currentRating', 'ratingChange',
  'lastSignal', 'daysSinceSignal', 'volume', 'sector', 'aiConfidence',
  'distFrom52wHighPct', 'distFrom52wLowPct', 'weeklyRating', 'combinedScore',
  'insiderLatestTransaction', 'insiderTotalValue', 'insiderValueLast30Days',
] as const

export function sortParam<K extends string>(fallback: SortLevel<K>, allowed: readonly K[]): UrlField<SortLevel<K>[]> {
  return {
    read: (params) => {
      const keys = params.get('sortBy')?.split(',') ?? []
      const dirs = params.get('sortDir')?.split(',') ?? []
      const seen = new Set<string>()
      const levels: SortLevel<K>[] = []
      keys.forEach((key, index) => {
        const dir = dirs[index]
        if (allowed.includes(key as K) && (dir === 'asc' || dir === 'desc') && !seen.has(key)) {
          seen.add(key)
          levels.push({ key: key as K, dir })
        }
      })
      return levels.length ? levels.slice(0, MAX_SORT_LEVELS) : [fallback]
    },
    write: (params, _key, levels) => {
      const serialized = serializeSort(levels)
      if (serialized) {
        params.set('sortBy', serialized.sortBy)
        params.set('sortDir', serialized.sortDir)
      }
    },
  }
}
