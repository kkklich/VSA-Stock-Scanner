// Archived at the owner's request (2026-10-29). Preserve their UI/algorithm
// code for reactivation, but hide stale saved selections and classic-only
// panels. Keep this policy aligned with backend app/analysis/method_status.py.
export const INACTIVE_METHOD_IDS = new Set(['vsa', 'glinicki', 'vsa3'])
export const isMethodActive = (id: string) => !INACTIVE_METHOD_IDS.has(id)
export const CLASSIC_VSA_ENABLED = isMethodActive('vsa')

export const CLASSIC_RANKING_COLUMNS = new Set([
  'rating', 'ratingChange', 'signal', 'daysSinceSignal', 'aiConfidence', 'trend',
])
