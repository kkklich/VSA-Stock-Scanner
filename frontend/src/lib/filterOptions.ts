// Shared filter option lists for ranking-table pages (Dashboard, Watchlist).

import type { SignalVerdict } from '../types'

export const SIGNAL_OPTIONS: (SignalVerdict | 'all')[] = [
  'all',
  'Strong Buy',
  'Buy',
  'Hold',
  'Sell',
  'Strong Sell',
]

export const RATING_OPTIONS = [
  { label: 'All ratings', value: 0 },
  { label: '70+ (strong)', value: 70 },
  { label: '90+ (elite)', value: 90 },
]
