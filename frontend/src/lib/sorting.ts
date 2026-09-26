// Multi-column sorting, shared by every sortable table in the app.
//
// A sort is an ordered list of levels: the first one is the order you see, the
// ones after it only break its ties. "Sector A→Z, best rating first" is two
// levels; one level is an ordinary single-column sort and is what the pages
// start with, so nothing looks different until the user asks for more.
//
// These helpers are pure — the pages own the state and the backend does the
// actual ordering (`sortBy`/`sortDir` carry the levels as comma-separated
// lists). Keeping the rules here means the table headers, the phone Sort menu
// and all five pages behave identically.

/** Which way a column is ordered. */
export type SortDir = 'asc' | 'desc'

/** One level of a sort: which column, and in which direction. */
export interface SortLevel<K extends string> {
  key: K
  dir: SortDir
}

/**
 * How many levels a sort may have. Two covers the common "group by sector,
 * best first"; three leaves room for one tie-break inside that. Deeper than
 * that and nobody can read the ordering off the table any more — and the
 * backend rejects it, so the two limits have to agree (`MAX_SORT_LEVELS` in
 * `app/routers/stocks.py`).
 */
export const MAX_SORT_LEVELS = 3

/** The direction a column starts in — labels ascend, numbers descend. */
export type InitialDir<K extends string> = (key: K) => SortDir

const flip = (dir: SortDir): SortDir => (dir === 'asc' ? 'desc' : 'asc')

/** Index of `key` in `levels`, or -1. */
export function levelIndex<K extends string>(levels: SortLevel<K>[], key: K): number {
  return levels.findIndex((l) => l.key === key)
}

/**
 * The new sort after the user clicked a column header (or picked one from the
 * phone menu).
 *
 * `additive` is the shift-click / "then by" gesture — it builds a deeper sort
 * instead of replacing the current one:
 *
 *   plain click   → sort by this column alone (flip the direction when it is
 *                   already the only level). Any extra levels are dropped,
 *                   which is what makes a plain click a reliable way back to a
 *                   simple, obvious ordering.
 *   shift-click   → a column that is not sorted on becomes the next level; one
 *                   that is cycles direction → removed, so the gesture that
 *                   added a level can also take it away. A sort is never left
 *                   empty: cycling the last remaining level puts it back to
 *                   its starting direction instead of clearing the table's
 *                   order entirely.
 *
 * At `MAX_SORT_LEVELS` an additive click on a new column replaces the deepest
 * level rather than doing nothing — silently ignoring a click reads as a bug.
 */
export function applySortClick<K extends string>(
  levels: SortLevel<K>[],
  key: K,
  { additive = false, initialDir }: { additive?: boolean; initialDir: InitialDir<K> },
): SortLevel<K>[] {
  const start = initialDir(key)

  if (!additive) {
    if (levels.length === 1 && levels[0].key === key) {
      return [{ key, dir: flip(levels[0].dir) }]
    }
    return [{ key, dir: start }]
  }

  const at = levelIndex(levels, key)
  if (at === -1) {
    const next = { key, dir: start }
    return levels.length < MAX_SORT_LEVELS
      ? [...levels, next]
      : [...levels.slice(0, MAX_SORT_LEVELS - 1), next]
  }

  const current = levels[at]
  if (current.dir === start) {
    // First shift-click on an existing level: flip it, keeping its position.
    return levels.map((l, i) => (i === at ? { ...l, dir: flip(l.dir) } : l))
  }
  if (levels.length === 1) {
    // Removing it would leave no ordering at all — cycle back instead.
    return [{ key, dir: start }]
  }
  return levels.filter((_, i) => i !== at)
}

/** Set one level's direction (the phone menu's explicit asc/desc buttons). */
export function setLevelDir<K extends string>(
  levels: SortLevel<K>[],
  key: K,
  dir: SortDir,
): SortLevel<K>[] {
  return levels.map((l) => (l.key === key ? { ...l, dir } : l))
}

/** Drop one level. The last remaining level is kept — a table is always ordered. */
export function removeLevel<K extends string>(
  levels: SortLevel<K>[],
  key: K,
): SortLevel<K>[] {
  if (levels.length <= 1) return levels
  const next = levels.filter((l) => l.key !== key)
  return next.length ? next : levels
}

/** Append a column as the next level (the phone menu's "then by" list). */
export function addLevel<K extends string>(
  levels: SortLevel<K>[],
  key: K,
  initialDir: InitialDir<K>,
): SortLevel<K>[] {
  return applySortClick(levels, key, { additive: true, initialDir })
}

/**
 * The levels as the two query parameters the API takes
 * (`sortBy=sector,currentRating&sortDir=asc,desc`). One level serialises to a
 * single value in each, which is byte-identical to what the app sent before
 * multi-column sorting existed.
 */
export function serializeSort<K extends string>(
  levels: SortLevel<K>[],
): { sortBy: string; sortDir: string } | null {
  if (!levels.length) return null
  return {
    sortBy: levels.map((l) => l.key).join(','),
    sortDir: levels.map((l) => l.dir).join(','),
  }
}

/**
 * A stable string for React effect dependencies / cache keys. The levels are
 * an array of objects, so a fresh render would otherwise look like a change.
 */
export function sortKey<K extends string>(levels: SortLevel<K>[]): string {
  return levels.map((l) => `${l.key}:${l.dir}`).join(',')
}

/** Drop levels whose column no longer exists (e.g. a renamed sort key). */
export function normalizeSort<K extends string>(
  levels: SortLevel<K>[],
  isValid: (key: K) => boolean,
  fallback: SortLevel<K>,
): SortLevel<K>[] {
  const seen = new Set<K>()
  const kept = levels.filter((l) => {
    if (!isValid(l.key) || seen.has(l.key)) return false
    seen.add(l.key)
    return true
  })
  return kept.length ? kept.slice(0, MAX_SORT_LEVELS) : [fallback]
}
