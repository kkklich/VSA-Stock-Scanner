// Column registry for the ranking / screener table (Filters page).
//
// Every column is driven entirely by data already in the ranking payload
// (ApiRankingItem) — no extra endpoint. Each entry carries its header label,
// server-side sort key, alignment, default visibility, an optional tooltip and
// a cell renderer, so the table can be rendered from a user-chosen subset of
// columns ("spreadsheet with superpowers"). The chosen subset is persisted per
// browser under RANKING_COLUMNS_KEY.

import type { ReactNode } from 'react'
import type { ApiRankingItem, RankingSortKey } from '../api/stocksApi'
import { RatingMeter, SignalBadge, Sparkline, TickerMark } from '../components/ui'
import { deltaTone, fmtCompactPln, fmtPct, fmtPrice } from './format'

/** localStorage key for the Filters-page column selection. */
export const RANKING_COLUMNS_KEY = 'stockpilot:ranking-columns:v1'

export type RankingColumnId =
  | 'company'
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

export interface RankingColumn {
  id: RankingColumnId
  /** Header text shown in the table. */
  label: string
  /** Label shown in the column-picker menu (defaults to `label`). */
  menuLabel?: string
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
  /** Optional plain-language header tooltip. */
  info?: string
  /** Renders the cell content for one row. */
  cell: (row: ApiRankingItem) => ReactNode
}

/**
 * One 52-week distance cell: the percentage plus a "NEW" chip when the latest
 * session actually set the extreme (a breakout/breakdown, not just proximity).
 */
function Range52wCell({
  pct,
  isNew,
  newTone,
}: {
  pct: number | null
  isNew: boolean
  newTone: string
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
          new
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
    label: 'Company',
    sortKey: 'ticker',
    align: 'left',
    sortAscFirst: true,
    required: true,
    defaultVisible: true,
    cell: (s) => (
      <div className="flex items-center gap-2.5">
        <TickerMark ticker={s.ticker} />
        <div className="min-w-0">
          <div className="font-semibold text-slate-100">{s.ticker}</div>
          <div className="max-w-[200px] truncate text-xs text-slate-500">{s.name}</div>
        </div>
      </div>
    ),
  },
  {
    id: 'sector',
    label: 'Sector',
    sortKey: 'sector',
    align: 'left',
    sortAscFirst: true,
    defaultVisible: true,
    cell: (s) => <span className="text-xs text-slate-400">{s.sector ?? '—'}</span>,
  },
  {
    id: 'lastPrice',
    label: 'Price',
    menuLabel: 'Last price',
    sortKey: 'lastPrice',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    cell: (s) => (
      <span className="tabular-nums text-slate-200">{fmtPrice(s.lastPrice)}</span>
    ),
  },
  {
    id: 'priceChangePct',
    label: 'Change',
    menuLabel: 'Price change',
    sortKey: 'priceChangePct',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    info: "The latest session's price change, percent.",
    cell: (s) => (
      <span className={'font-medium tabular-nums ' + deltaTone(s.priceChangePct)}>
        {fmtPct(s.priceChangePct)}
      </span>
    ),
  },
  {
    id: 'dist52wHigh',
    label: 'From 52w high',
    sortKey: 'distFrom52wHighPct',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    info: 'How far below the 52-week high the last close sits. 0% means it closed at the high; a “NEW” chip marks a session that set a fresh 52-week high.',
    cell: (s) => (
      <Range52wCell
        pct={s.distFrom52wHighPct}
        isNew={s.isNew52wHigh}
        newTone="bg-emerald-500/15 text-emerald-400 ring-emerald-500/30"
      />
    ),
  },
  {
    id: 'dist52wLow',
    label: 'From 52w low',
    sortKey: 'distFrom52wLowPct',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    info: 'How far above the 52-week low the last close sits. A “NEW” chip marks a session that set a fresh 52-week low.',
    cell: (s) => (
      <Range52wCell
        pct={s.distFrom52wLowPct}
        isNew={s.isNew52wLow}
        newTone="bg-rose-500/15 text-rose-400 ring-rose-500/30"
      />
    ),
  },
  {
    id: 'rating',
    label: 'Rating (0–100)',
    menuLabel: 'VSA rating',
    sortKey: 'currentRating',
    align: 'left',
    sortAscFirst: false,
    defaultVisible: true,
    info: 'VSA score with time decay: recent bullish signals push it above 50, bearish ones below.',
    cell: (s) => <RatingMeter rating={s.currentRating} />,
  },
  {
    id: 'ratingChange',
    label: 'Rating Δ',
    menuLabel: 'Rating change',
    sortKey: 'ratingChange',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    info: 'Change in the VSA rating versus the previous session — the day-over-day mover.',
    cell: (s) => (
      <span className={'tabular-nums ' + deltaTone(s.ratingChange)}>
        {ratingDelta(s.ratingChange)}
      </span>
    ),
  },
  {
    id: 'signal',
    label: 'Signal',
    sortKey: 'lastSignal',
    align: 'left',
    sortAscFirst: false,
    defaultVisible: true,
    info: 'Verdict from the most recent VSA pattern: Spring / SOS → Strong Buy, Successful Test → Buy, No Demand → Sell, Upthrust / SOW → Strong Sell.',
    cell: (s) => <SignalBadge verdict={s.lastSignal} />,
  },
  {
    id: 'daysSinceSignal',
    label: 'Days ago',
    menuLabel: 'Signal age',
    sortKey: 'daysSinceSignal',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: true,
    info: 'Sessions since the last VSA pattern fired. Fresh signals matter most in VSA — old ones fade.',
    cell: (s) => (
      <span className="tabular-nums text-xs text-slate-400">
        {s.daysSinceSignal === 999 ? '—' : s.daysSinceSignal}
      </span>
    ),
  },
  {
    id: 'volume',
    label: 'Volume',
    menuLabel: 'Median volume',
    sortKey: 'volume',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    info: '20-session median daily volume, in shares — a liquidity gauge.',
    cell: (s) => (
      <span className="tabular-nums text-slate-300">{fmtCompactPln(s.volume)}</span>
    ),
  },
  {
    id: 'aiConfidence',
    label: 'AI',
    menuLabel: 'AI confidence',
    sortKey: 'aiConfidence',
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    info: 'Confidence of the built-in AI-insight engine in its verdict, 0–100.',
    cell: (s) => <span className="tabular-nums text-slate-300">{s.aiConfidence}</span>,
  },
  {
    id: 'trend',
    label: 'Trend',
    menuLabel: 'Trend (sparkline)',
    sortKey: null,
    align: 'right',
    sortAscFirst: false,
    defaultVisible: false,
    info: 'Recent price path over the analysis window.',
    cell: (s) => (
      <span className="inline-flex justify-end">
        <Sparkline data={s.sparkline} />
      </span>
    ),
  },
]

/** Sort keys whose first click should sort ascending (the text columns). */
export const ASC_FIRST_SORT_KEYS: RankingSortKey[] = RANKING_COLUMNS.filter(
  (c) => c.sortAscFirst && c.sortKey,
).map((c) => c.sortKey as RankingSortKey)

/** The user's stored show/hide choices; a missing key falls back to the default. */
export type ColumnVisibility = Partial<Record<RankingColumnId, boolean>>

/** Whether a column is currently shown (required columns always are). */
export function isColumnVisible(col: RankingColumn, stored: ColumnVisibility): boolean {
  if (col.required) return true
  return stored[col.id] ?? col.defaultVisible
}

/** The visible columns, in table order. Never empty (identity column is locked). */
export function visibleColumns(stored: ColumnVisibility): RankingColumn[] {
  return RANKING_COLUMNS.filter((c) => isColumnVisible(c, stored))
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
