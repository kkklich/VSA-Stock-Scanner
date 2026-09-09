// Column registry for every ranking table in the app — the Dashboard, the
// Watchlist and the Filters screener all render from this one list.
//
// Every column is driven entirely by data already in the ranking payload
// (ApiRankingItem) — no extra endpoint. Each entry carries its i18n label key,
// server-side sort key, alignment, default visibility, an optional tooltip and
// a cell renderer, so a table can be rendered from a user-chosen subset of
// columns ("spreadsheet with superpowers").
//
// The chosen subset is shared by all three pages and persisted per browser
// under RANKING_COLUMNS_KEY, so hiding a column hides it everywhere — on the
// wide-screen tables AND in the phone/tablet card lists, which render from the
// same list via `mobile` slots (see `RankingCard`).

import type { ReactNode } from 'react'
import type { TFunction } from 'i18next'
import { Star } from 'lucide-react'
import type { ApiRankingItem, RankingSortKey } from '../api/stocksApi'
import {
  CompanyLink,
  RatingMeter,
  SignalBadge,
  Sparkline,
  TickerMark,
  WeeklyBadge,
} from '../components/ui'
import { deltaTone, fmtCompactPln, fmtPct, fmtPrice } from './format'

/** localStorage key for the shared ranking-column selection. */
export const RANKING_COLUMNS_KEY = 'stockpilot:ranking-columns:v1'

/**
 * localStorage key for the shared ranking-column ORDER. Kept separate from the
 * visibility map so an existing selection keeps working untouched: a browser
 * that has only ever stored visibility simply has no order and gets the
 * registry one.
 */
export const RANKING_COLUMN_ORDER_KEY = 'stockpilot:ranking-column-order:v1'

export type RankingColumnId =
  | 'company'
  | 'name'
  | 'sector'
  | 'lastPrice'
  | 'priceChangePct'
  | 'dist52wHigh'
  | 'dist52wLow'
  | 'rating'
  | 'ratingChange'
  | 'signal'
  | 'daysSinceSignal'
  | 'volume'
  | 'aiConfidence'
  | 'trend'

/**
 * Where a column goes in the phone/tablet card layout.
 *  - `identity` — the ticker/name block in the card head (never a chip).
 *  - `price`    — the right-hand price block in the card head.
 *  - `chip`     — a labelled value in the card's wrapped detail row (default).
 */
export type MobileSlot = 'identity' | 'price' | 'chip'

/** Everything a cell may need beyond the row itself. */
export interface CellContext {
  t: TFunction
  /** Present only on pages with favorites (Dashboard, Watchlist). */
  starred?: boolean
  onToggleStar?: (ticker: string) => void
}

export interface RankingColumn {
  id: RankingColumnId
  /** i18n key for the header text shown in the table. */
  labelKey: string
  /** i18n key for the column-picker menu label (defaults to `labelKey`). */
  menuLabelKey?: string
  /**
   * i18n key for the label on a phone card chip (defaults to `labelKey`).
   * Only for headers whose wording is fine in a table but repeats badly once
   * per card — "Rating (0–100)" is the range hint the header tooltip already
   * explains, so the chip just says "Rating".
   */
  mobileLabelKey?: string
  /** i18n key for the plain-language header tooltip. */
  infoKey?: string
  /** i18n key for the small second line under the header. */
  subLabelKey?: string
  /** Server-side sort key; null = the column can't be sorted (e.g. sparkline). */
  sortKey: RankingSortKey | null
  /** Right-align (numbers) vs left (text / badges). */
  align: 'left' | 'right'
  /** First click on the header sorts ascending (text) vs descending (metrics). */
  sortAscFirst: boolean
  /** The identity column — always shown, can't be hidden. */
  required?: boolean
  /** Visible by default, before the user touches the picker. */
  defaultVisible: boolean
  /** Roughly how wide this column needs to be; sums into the table min-width. */
  width: number
  /** Placement in the phone/tablet card list. Defaults to `chip`. */
  mobile?: MobileSlot
  /** Renders the cell content for one row. */
  cell: (row: ApiRankingItem, ctx: CellContext) => ReactNode
}

/**
 * One 52-week distance cell: the percentage plus a "NEW" chip when the latest
 * session actually set the extreme (a breakout/breakdown, not just proximity).
 */
function Range52wCell({
  pct,
  isNew,
  newTone,
  newLabel,
}: {
  pct: number | null
  isNew: boolean
  newTone: string
  newLabel: string
}) {
  if (pct === null) return <span className="text-slate-600">—</span>
  return (
    <span className="inline-flex items-center justify-end gap-1.5">
      {isNew && (
        <span
          className={
            'rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide ring-1 ' +
            newTone
          }
        >
          {newLabel}
        </span>
      )}
      <span className="tabular-nums text-slate-300">{fmtPct(pct)}</span>
    </span>
  )
}

/** Signed rating delta, shown "0" (not "+0") when unchanged. */
function ratingDelta(change: number): string {
  return change > 0 ? `+${change}` : String(change)
}

/**
 * All columns, in table order (left → right). The picker shows them in this
 * order too; `required` columns are locked on.
 */
export const RANKING_COLUMNS: RankingColumn[] = [
  {
    id: 'company',
    labelKey: 'columns.label.company',
    sortKey: 'ticker',
    align: 'left',
    sortAscFirst: true,
    required: true,
    defaultVisible: true,
    width: 230,
    mobile: 'identity',
    // Ticker and company name in one cell. The name gets its own sortable
    // column too (off by default) for anyone who wants to sort A→Z by it.
    cell: (s, ctx) => (
      <div className="flex items-center gap-2.5">
        {ctx.onToggleStar && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              ctx.onToggleStar?.(s.ticker)
            }}
            className="shrink-0 text-slate-600 hover:text-amber-400"
            aria-label={ctx.t('dashboard.toggleFavorite')}
          >
            <Star size={15} className={ctx.starred ? 'fill-amber-400 text-amber-400' : ''} />
          </button>
        )}
        <CompanyLink ticker={s.ticker} title={s.name} className="flex items-center gap-2.5">
          <TickerMark ticker={s.ticker} />
          <span className="min-w-0">
            <span className="block font-semibold text-slate-100">{s.ticker}</span>
            <span className="block max-w-[190px] truncate text-xs text-slate-500">
              {s.name}
            </span>
          </span>
        </CompanyLink>
      </div>
    ),
  },
  {
    id: 'name',
    labelKey: 'columns.label.name',
    sortKey: 'name',
    align: 'left',
    sortAscFirst: true,
    defaultVisible: false,
    width: 200,
    mobile: 'identity',
    cell: (s) => (
      <CompanyLink
        ticker={s.ticker}
        title={s.name}
        className="block max-w-[220px] truncate text-slate-400 hover:text-slate-200"
      >
        {s.name}
      </CompanyLink>
    ),
  },
  {
    id: 'sector',
    labelKey: 'columns.label.sector',
    sortKey: 'sector',
    align: 'left',
    sortAscFirst: true,
    defaultVisible: false,
    width: 150,
    cell: (s) => <span className="text-xs text-slate-400">{s.sector ?? '—'}</span>,
  },
  {
    id: 'lastPrice',
    labelKey: 'columns.label.lastPrice',
    menuLabelKey: 'columns.menu.lastPrice',
    sortKey: 'lastPrice',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    width: 130,
    mobile: 'price',
    cell: (s, ctx) => (
      <span className="whitespace-nowrap font-medium tabular-nums text-slate-200">
        {fmtPrice(s.lastPrice)} {ctx.t('common.pln')}
      </span>
    ),
  },
  {
    id: 'priceChangePct',
    labelKey: 'columns.label.priceChangePct',
    menuLabelKey: 'columns.menu.priceChangePct',
    infoKey: 'columns.info.priceChangePct',
    sortKey: 'priceChangePct',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    width: 110,
    mobile: 'price',
    cell: (s) => (
      <span className={'font-medium tabular-nums ' + deltaTone(s.priceChangePct)}>
        {fmtPct(s.priceChangePct)}
      </span>
    ),
  },
  {
    id: 'dist52wHigh',
    labelKey: 'columns.label.dist52wHigh',
    infoKey: 'columns.info.dist52wHigh',
    sortKey: 'distFrom52wHighPct',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    width: 140,
    cell: (s, ctx) => (
      <Range52wCell
        pct={s.distFrom52wHighPct}
        isNew={s.isNew52wHigh}
        newLabel={ctx.t('columns.new')}
        newTone="bg-emerald-500/15 text-emerald-400 ring-emerald-500/30"
      />
    ),
  },
  {
    id: 'dist52wLow',
    labelKey: 'columns.label.dist52wLow',
    infoKey: 'columns.info.dist52wLow',
    sortKey: 'distFrom52wLowPct',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    width: 140,
    cell: (s, ctx) => (
      <Range52wCell
        pct={s.distFrom52wLowPct}
        isNew={s.isNew52wLow}
        newLabel={ctx.t('columns.new')}
        newTone="bg-rose-500/15 text-rose-400 ring-rose-500/30"
      />
    ),
  },
  {
    id: 'rating',
    labelKey: 'columns.label.rating',
    menuLabelKey: 'columns.menu.rating',
    mobileLabelKey: 'columns.mobile.rating',
    infoKey: 'columns.info.rating',
    sortKey: 'currentRating',
    align: 'left',
    sortAscFirst: false,
    defaultVisible: true,
    width: 175,
    cell: (s) => <RatingMeter rating={s.currentRating} />,
  },
  {
    id: 'ratingChange',
    labelKey: 'columns.label.ratingChange',
    menuLabelKey: 'columns.menu.ratingChange',
    infoKey: 'columns.info.ratingChange',
    sortKey: 'ratingChange',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    width: 110,
    cell: (s) => (
      <span className={'tabular-nums ' + deltaTone(s.ratingChange)}>
        {ratingDelta(s.ratingChange)}
      </span>
    ),
  },
  {
    id: 'signal',
    labelKey: 'columns.label.signal',
    infoKey: 'columns.info.signal',
    sortKey: 'lastSignal',
    align: 'left',
    sortAscFirst: false,
    defaultVisible: true,
    width: 190,
    // The weekly (multi-timeframe) agreement chip rides along with the verdict
    // it qualifies — it is a footnote on the signal, not a column of its own.
    cell: (s) => (
      <div className="flex flex-nowrap items-center gap-1.5">
        <SignalBadge verdict={s.lastSignal} />
        <WeeklyBadge
          agreement={s.weeklyAgreement}
          rating={s.weeklyRating}
          signal={s.weeklySignal}
        />
      </div>
    ),
  },
  {
    id: 'daysSinceSignal',
    labelKey: 'columns.label.daysSinceSignal',
    menuLabelKey: 'columns.menu.daysSinceSignal',
    infoKey: 'columns.info.daysSinceSignal',
    sortKey: 'daysSinceSignal',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    width: 110,
    cell: (s) => (
      <span className="tabular-nums text-xs text-slate-400">
        {s.daysSinceSignal === 999 ? '—' : s.daysSinceSignal}
      </span>
    ),
  },
  {
    id: 'volume',
    labelKey: 'columns.label.volume',
    menuLabelKey: 'columns.menu.volume',
    infoKey: 'columns.info.volume',
    sortKey: 'volume',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    width: 120,
    cell: (s) => (
      <span className="tabular-nums text-slate-300">{fmtCompactPln(s.volume)}</span>
    ),
  },
  {
    id: 'aiConfidence',
    labelKey: 'columns.label.aiConfidence',
    menuLabelKey: 'columns.menu.aiConfidence',
    infoKey: 'columns.info.aiConfidence',
    sortKey: 'aiConfidence',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    width: 90,
    cell: (s) => <span className="tabular-nums text-slate-300">{s.aiConfidence}</span>,
  },
  {
    id: 'trend',
    labelKey: 'columns.label.trend',
    menuLabelKey: 'columns.menu.trend',
    infoKey: 'columns.info.trend',
    sortKey: null,
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    width: 110,
    cell: (s) => (
      <span className="inline-flex justify-end">
        <Sparkline data={s.sparkline} />
      </span>
    ),
  },
]

/** The user's stored show/hide choices; a missing key falls back to the default. */
export type ColumnVisibility = Partial<Record<RankingColumnId, boolean>>

/** Whether a column is currently shown (required columns always are). */
export function isColumnVisible(col: RankingColumn, stored: ColumnVisibility): boolean {
  if (col.required) return true
  return stored[col.id] ?? col.defaultVisible
}

/* ── Column order ─────────────────────────────────────────────────────────
   The user can move a column left or right in the table; the arrangement is
   stored as a plain list of ids (RANKING_COLUMN_ORDER_KEY) and shared by the
   three ranking pages, exactly like the visibility map. Everything goes
   through `normalizeOrder`, so a stored list that is stale (a column was
   removed from the app), partial (written before a column was added) or
   corrupt still yields a complete, usable order. */

/** The user's left → right column arrangement; `[]` means "registry order". */
export type ColumnOrder = RankingColumnId[]

/** The ids of the pinned columns, in registry order. */
const REQUIRED_IDS: RankingColumnId[] = RANKING_COLUMNS.filter((c) => c.required).map(
  (c) => c.id,
)

/**
 * A complete, de-duplicated order: the stored ids first (unknown ones dropped),
 * then any registry column the stored list never mentioned, in registry order —
 * so a column added in a later release appears instead of vanishing. The locked
 * identity column is pinned to the front: it is the row's anchor, and the rank
 * number sits beside it.
 */
export function normalizeOrder(order: ColumnOrder | null | undefined): ColumnOrder {
  const known = new Map(RANKING_COLUMNS.map((c) => [c.id, c]))
  const seen = new Set<RankingColumnId>()
  const out: RankingColumnId[] = []

  for (const id of order ?? []) {
    if (known.has(id) && !seen.has(id)) {
      seen.add(id)
      out.push(id)
    }
  }
  for (const col of RANKING_COLUMNS) {
    if (!seen.has(col.id)) out.push(col.id)
  }
  return [...REQUIRED_IDS, ...out.filter((id) => !REQUIRED_IDS.includes(id))]
}

/** Every registry column, in the user's order. */
export function orderedColumns(order?: ColumnOrder | null): RankingColumn[] {
  const byId = new Map(RANKING_COLUMNS.map((c) => [c.id, c]))
  return normalizeOrder(order).map((id) => byId.get(id) as RankingColumn)
}

/**
 * Move one column one place towards the front (`-1`) or the back (`+1`) and
 * return the full explicit order. Pinned columns don't move and nothing moves
 * past them; a move that would run off either end is a no-op (the order comes
 * back unchanged).
 *
 * The order carries every column, hidden ones included, so the arrangement the
 * user builds survives switching a column back on. But a *shown* column hops
 * straight over hidden neighbours when `stored` is supplied: with most columns
 * off by default, stepping one slot at a time would often leave the table
 * looking untouched after a click.
 */
export function moveColumn(
  order: ColumnOrder | null | undefined,
  id: RankingColumnId,
  delta: -1 | 1,
  stored?: ColumnVisibility,
): ColumnOrder {
  const list = normalizeOrder(order)
  const byId = new Map(RANKING_COLUMNS.map((c) => [c.id, c]))
  const col = byId.get(id)
  const from = list.indexOf(id)
  if (!col || from === -1 || REQUIRED_IDS.includes(id)) return list

  // Land next to the nearest neighbour that is actually on screen; for a
  // hidden column (or with no visibility map) that is simply the next slot.
  const skipHidden = stored !== undefined && isColumnVisible(col, stored)
  let to = from + delta
  while (
    skipHidden &&
    to >= 0 &&
    to < list.length &&
    !isColumnVisible(byId.get(list[to]) as RankingColumn, stored)
  ) {
    to += delta
  }
  if (to < 0 || to >= list.length || REQUIRED_IDS.includes(list[to])) return list

  const next = [...list]
  next.splice(from, 1)
  next.splice(to, 0, id)
  return next
}

/** Whether `moveColumn` with these arguments would actually change anything. */
export function canMoveColumn(
  order: ColumnOrder | null | undefined,
  id: RankingColumnId,
  delta: -1 | 1,
  stored?: ColumnVisibility,
): boolean {
  const list = normalizeOrder(order)
  const moved = moveColumn(list, id, delta, stored)
  return moved.some((columnId, i) => columnId !== list[i])
}

/** True when the user's order differs from the registry's. */
export function orderCustomized(order: ColumnOrder | null | undefined): boolean {
  const list = normalizeOrder(order)
  return RANKING_COLUMNS.some((col, i) => list[i] !== col.id)
}

/**
 * The visible columns, left → right. Never empty (the identity column is
 * locked on). `order` is the user's own arrangement; omit it for registry order.
 */
export function visibleColumns(
  stored: ColumnVisibility,
  order?: ColumnOrder,
): RankingColumn[] {
  return orderedColumns(order).filter((c) => isColumnVisible(c, stored))
}

/** True when any non-required column differs from its default visibility. */
export function columnsCustomized(stored: ColumnVisibility): boolean {
  return RANKING_COLUMNS.some(
    (c) => !c.required && (stored[c.id] ?? c.defaultVisible) !== c.defaultVisible,
  )
}

/** Flip one column's visibility; required columns are left untouched. */
export function toggleColumnVisibility(
  stored: ColumnVisibility,
  id: RankingColumnId,
): ColumnVisibility {
  const col = RANKING_COLUMNS.find((c) => c.id === id)
  if (!col || col.required) return stored
  const currentlyVisible = stored[id] ?? col.defaultVisible
  return { ...stored, [id]: !currentlyVisible }
}

/** The header label for a column, translated. */
export function columnLabel(col: RankingColumn, t: TFunction): string {
  return t(col.labelKey)
}

/** The column-picker menu label, translated (falls back to the header label). */
export function columnMenuLabel(col: RankingColumn, t: TFunction): string {
  return t(col.menuLabelKey ?? col.labelKey)
}

/**
 * Minimum table width for a set of columns, so the layout never crushes and the
 * page (not an inner scroller) scrolls sideways when it has to.
 */
export function tableMinWidth(columns: { width: number }[], extra = 0): number {
  return columns.reduce((sum, c) => sum + c.width, 0) + extra
}

/* ── Render columns ───────────────────────────────────────────────────────
   The tables and card lists render from `RenderColumn`, a translated,
   already-resolved shape. Registry columns become render columns via
   `toRenderColumns`; the Dashboard builds a few extra ones of its own (one per
   selected trading method, plus the combined score) and splices them in, so a
   dynamic column and a registry column travel down exactly the same path. */

export interface RenderColumn {
  /** Unique key (a RankingColumnId, or a method id for the dynamic ones). */
  key: string
  /** Translated header text. */
  label: string
  /** Short label for the phone/tablet card chip (defaults to `label`). */
  mobileLabel?: string
  /** Translated header tooltip. */
  info?: string
  /** Translated second line under the header. */
  subLabel?: string
  /** Extra classes on the `<th>` (the method columns use `normal-case`). */
  headerClassName?: string
  sortKey: RankingSortKey | null
  align: 'left' | 'right'
  width: number
  mobile?: MobileSlot
  cell: (row: ApiRankingItem, ctx: CellContext) => ReactNode
}

/** Resolve registry columns into translated render columns. */
export function toRenderColumns(
  columns: RankingColumn[],
  t: TFunction,
): RenderColumn[] {
  return columns.map((col) => ({
    key: col.id,
    label: columnLabel(col, t),
    mobileLabel: col.mobileLabelKey ? t(col.mobileLabelKey) : undefined,
    info: col.infoKey ? t(col.infoKey) : undefined,
    subLabel: col.subLabelKey ? t(col.subLabelKey) : undefined,
    sortKey: col.sortKey,
    align: col.align,
    width: col.width,
    mobile: col.mobile,
    cell: col.cell,
  }))
}

/**
 * Insert extra columns directly after the column with `afterKey` — the
 * Dashboard uses it to keep its per-method columns next to the signal they
 * qualify, rather than exiled to the right-hand edge. Appends when the anchor
 * is not visible.
 */
export function spliceAfter(
  columns: RenderColumn[],
  afterKey: string,
  extra: RenderColumn[],
): RenderColumn[] {
  if (extra.length === 0) return columns
  const at = columns.findIndex((c) => c.key === afterKey)
  if (at === -1) return [...columns, ...extra]
  return [...columns.slice(0, at + 1), ...extra, ...columns.slice(at + 1)]
}

/** Direction a column should take on its first click (text A→Z, metrics high→low). */
export function initialSortDir(sortKey: RankingSortKey): 'asc' | 'desc' {
  const col = RANKING_COLUMNS.find((c) => c.sortKey === sortKey)
  return col?.sortAscFirst ? 'asc' : 'desc'
}
