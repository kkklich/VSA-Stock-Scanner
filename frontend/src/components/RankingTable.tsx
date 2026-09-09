// The two layouts every ranking list uses, both rendered from the SAME column
// list (see `lib/rankingColumns.tsx`):
//
//   RankingTable    — the wide-screen table (lg+), sorted by its headers.
//   RankingCardList — the phone/tablet stacked cards (below lg).
//
// Sharing the column list is the point: when the user hides a column in the
// picker it disappears from both, so a phone shows the same information a
// desktop does rather than a fixed layout of its own. Columns land in the card
// by their `mobile` slot — `identity` in the head, `price` in the head's right
// block, everything else as a labelled chip in the detail row.

import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { InfoTip, SortHeader } from './ui'
import type { CellContext, RenderColumn } from '../lib/rankingColumns'
import type { ApiRankingItem, RankingSortKey, SortDir } from '../api/stocksApi'

/** A ranking row plus the client-only favorite flag the pages overlay on it. */
export type RankingRow = ApiRankingItem & { starred?: boolean }

interface SharedProps {
  columns: RenderColumn[]
  rows: RankingRow[]
  onOpen: (ticker: string) => void
  /** Toggle favorite; omit on pages without favorites (the screener). */
  onToggleStar?: (ticker: string) => void
  /** Show a 1-based rank number before each row. */
  showRank?: boolean
  /** Rank of the first row (for paginated pages); defaults to 1. */
  rankOffset?: number
}

/* ── Wide-screen table (lg+) ─────────────────────────────────────────────── */

export function RankingTable({
  columns,
  rows,
  onOpen,
  onToggleStar,
  showRank = false,
  rankOffset = 1,
  minWidth,
  sortBy,
  sortDir,
  onSort,
  footer,
  className = '',
}: SharedProps & {
  /** Table min-width in px — computed from the visible columns by the page. */
  minWidth: number
  sortBy: RankingSortKey
  sortDir: SortDir
  onSort: (col: RankingSortKey) => void
  /** Rendered inside the table's card, under the table (e.g. a pager). */
  footer?: ReactNode
  className?: string
}) {
  const { t } = useTranslation()

  // No overflow wrapper: the table scrolls with the page so its header can stay
  // pinned (position: sticky) as you scroll; min-width keeps the columns from
  // crushing. It is wide, so it only appears from lg up — phones and tablets
  // get RankingCardList instead and never scroll sideways.
  return (
    <div
      className={
        'hidden rounded-xl border border-slate-800 bg-slate-900/40 lg:block ' + className
      }
      style={{ minWidth }}
    >
      <table className="w-full text-sm" style={{ minWidth }}>
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
            {showRank && (
              <th className="sticky top-0 z-10 w-12 bg-slate-900 px-4 py-3 font-medium shadow-[inset_0_-1px_0_var(--color-slate-800)]">
                {t('columns.label.rank')}
              </th>
            )}
            {columns.map((col) =>
              col.sortKey ? (
                <SortHeader
                  key={col.key}
                  label={col.label}
                  col={col.sortKey}
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  align={col.align}
                  info={col.info}
                  subLabel={col.subLabel}
                  className={
                    (col.align === 'right' ? 'text-right ' : '') +
                    (col.headerClassName ?? '')
                  }
                />
              ) : (
                // Unsortable (the sparkline, the per-method scores): a plain
                // header with the same chrome, tooltip included.
                <th
                  key={col.key}
                  className={
                    'sticky top-0 z-10 bg-slate-900 px-4 py-3 font-medium shadow-[inset_0_-1px_0_var(--color-slate-800)] ' +
                    (col.align === 'right' ? 'text-right ' : '') +
                    (col.headerClassName ?? '')
                  }
                >
                  <span
                    className={
                      'inline-flex items-center gap-1 ' +
                      (col.align === 'right' ? 'justify-end' : '')
                    }
                  >
                    <span className="leading-tight">{col.label}</span>
                    {col.info && <InfoTip align="center" text={col.info} />}
                  </span>
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.ticker}
              onClick={() => onOpen(row.ticker)}
              tabIndex={0}
              aria-label={t('dashboard.openDetails', {
                ticker: row.ticker,
                name: row.name,
              })}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onOpen(row.ticker)
                }
              }}
              className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/30 focus:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50"
            >
              {showRank && (
                <td className="px-4 py-3 text-center tabular-nums text-slate-500">
                  {rankOffset + i}
                </td>
              )}
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={
                    'px-4 py-3 ' + (col.align === 'right' ? 'text-right' : '')
                  }
                >
                  {col.cell(row, { t, starred: row.starred, onToggleStar })}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {footer}
    </div>
  )
}

/* ── Phone / tablet cards (below lg) ─────────────────────────────────────── */

export function RankingCardList({
  columns,
  rows,
  onOpen,
  onToggleStar,
  showRank = false,
  rankOffset = 1,
}: SharedProps) {
  const { t } = useTranslation()

  const identity = columns.filter((c) => c.mobile === 'identity')
  const price = columns.filter((c) => c.mobile === 'price')
  const chips = columns.filter((c) => (c.mobile ?? 'chip') === 'chip')

  return (
    <ul className="flex flex-col gap-2 lg:hidden">
      {rows.map((row, i) => {
        const ctx: CellContext = { t, starred: row.starred, onToggleStar }
        return (
          <li key={row.ticker}>
            <div
              role="button"
              tabIndex={0}
              aria-label={t('dashboard.openDetails', {
                ticker: row.ticker,
                name: row.name,
              })}
              onClick={() => onOpen(row.ticker)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onOpen(row.ticker)
                }
              }}
              className="flex cursor-pointer flex-col gap-2 rounded-xl border border-slate-800 bg-slate-900/40 p-3 transition-colors hover:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50"
            >
              <div className="flex items-start gap-3">
                {showRank && (
                  <span className="w-5 shrink-0 pt-0.5 text-center text-sm font-semibold tabular-nums text-slate-500">
                    {rankOffset + i}
                  </span>
                )}
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  {identity.map((col) => (
                    <div key={col.key} className="min-w-0">
                      {col.cell(row, ctx)}
                    </div>
                  ))}
                </div>
                {price.length > 0 && (
                  <div className="flex shrink-0 flex-col items-end gap-0.5 text-right">
                    {price.map((col) => (
                      <div key={col.key}>{col.cell(row, ctx)}</div>
                    ))}
                  </div>
                )}
              </div>

              {chips.length > 0 && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-slate-800/60 pt-2">
                  {chips.map((col) => (
                    <span
                      key={col.key}
                      className="flex min-w-0 items-center gap-1.5 text-xs text-slate-500"
                    >
                      <span className="shrink-0">{col.mobileLabel ?? col.label}</span>
                      {col.cell(row, ctx)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
