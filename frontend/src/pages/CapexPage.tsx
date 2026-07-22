// Capex page — how much money each company invests in its own business.
//
// Capital expenditure (capex) is the cash spent on plants, machines,
// buildings and software: the "purchase of property, plant and equipment"
// line of the cash-flow statement. Absolute amounts favour giants, so the
// screen also shows capex as a share of revenue (capital intensity) and of
// operating cash flow (is the investment self-funded?).
//
// Figures come from stored Yahoo cash-flow statements, refreshed with the
// weekly fundamentals pass — never a live fetch.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Card, InfoTip, SortHeader, TickerMark } from '../components/ui'
import { useCapex } from '../hooks/useCapex'
import { useCompanies } from '../hooks/useCompanies'
import type { ApiCapexItem, CapexSortKey, SortDir } from '../api/stocksApi'
import { deltaTone, fmtCompactPln, fmtPct } from '../lib/format'

const PAGE_SIZE = 25

/** Columns that read naturally A→Z on the first click. */
const TEXT_COLUMNS: CapexSortKey[] = ['ticker', 'name', 'sector']

/** Money in the statement's own currency — never assume PLN. */
function fmtMoney(value: number | null, currency: string | null): string {
  if (value == null) return '—'
  return `${fmtCompactPln(value)} ${currency ?? ''}`.trim()
}

/**
 * Colour for "capex vs operating cash flow": comfortably self-funded below
 * 100%, stretched above it. Deliberately not green/red — outspending cash
 * flow is a growth investment as often as it is a warning, so the scale is
 * neutral-to-amber rather than good/bad.
 */
function ocfTone(pct: number | null): string {
  if (pct == null) return 'text-slate-600'
  if (pct > 100) return 'text-amber-400'
  return 'text-slate-200'
}

/** A figure that is missing rather than zero. */
function Blank() {
  return <span className="text-slate-600">—</span>
}

export function CapexPage() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [sector, setSector] = useState('all')
  // Amounts in different currencies don't compare (a forint figure would top
  // a zloty list on unit size alone), so the screen starts with the zloty
  // reporters — the comparable set for a GPW screen.
  const [currency, setCurrency] = useState('PLN')
  const [withData, setWithData] = useState(true)
  const [sortBy, setSortBy] = useState<CapexSortKey>('capex')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(q)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [q])

  const { companies } = useCompanies()
  const sectors = useMemo(() => {
    const set = new Set<string>()
    for (const c of companies) if (c.sector) set.add(c.sector)
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [companies])

  const { items, meta, loading, loadingMore, error, hasMore, refetch } = useCapex({
    q: search.trim() || undefined,
    sector,
    currency,
    withData,
    page,
    pageSize: PAGE_SIZE,
    sortBy,
    sortDir,
  })

  const totalCount = meta?.totalCount ?? 0

  // Infinite scroll: derive the next page from how many rows are already
  // loaded, so a double-fire of the observer can't skip a page.
  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) return
    setPage(Math.floor(items.length / PAGE_SIZE) + 1)
  }, [loading, loadingMore, hasMore, items.length])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore()
      },
      { rootMargin: '300px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [loadMore])

  const onSort = (col: CapexSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      setSortDir(TEXT_COLUMNS.includes(col) ? 'asc' : 'desc')
    }
    setPage(1)
  }

  const noDataAtAll = meta !== null && meta.withDataCount === 0

  return (
    <div className="space-y-4 p-4 md:p-6">
      {/* Header + what this means */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">
            Investment spending — how much each company invests
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-400">
            <span className="text-slate-200">Capital expenditure (capex)</span>{' '}
            is the money a company puts into its own business — factories,
            machines, buildings, software. A company that keeps investing is
            building future capacity; one whose capex has collapsed is often
            harvesting what it already has. Because a giant always outspends a
            small firm in absolute terms, the two percentage columns matter
            more than the amount.
          </p>
        </div>
        {meta?.asOf && (
          <span className="text-xs text-slate-500">
            Latest reported period {meta.asOf}
          </span>
        )}
      </div>

      {/* Filters */}
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search ticker or name…"
          className="w-52 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
        />
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Sector
          <select
            value={sector}
            onChange={(e) => {
              setSector(e.target.value)
              setPage(1)
            }}
            className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 focus:border-slate-500 focus:outline-none"
          >
            <option value="all">All sectors</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Reported in
          <select
            value={currency}
            onChange={(e) => {
              setCurrency(e.target.value)
              setPage(1)
            }}
            className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 focus:border-slate-500 focus:outline-none"
          >
            <option value="PLN">Złoty (PLN)</option>
            <option value="all">Any currency</option>
          </select>
          <InfoTip text="A few GPW-listed companies are foreign issuers reporting in EUR, USD, HUF or CZK. Their amounts are not comparable with złoty ones — 580 billion forint is far less money than 30 billion złoty — so the screen shows złoty reporters by default. The two percentage columns stay comparable across all currencies." />
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={!withData}
            onChange={(e) => {
              setWithData(!e.target.checked)
              setPage(1)
            }}
            className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900"
          />
          Show companies with no reported capex
          <InfoTip text="Yahoo has no usable cash-flow statement for some companies. Those rows are blank, not zero — 'not reported' is not 'invested nothing'." />
        </label>
        {meta && !loading && (
          <span className="ml-auto text-xs text-slate-500">
            {totalCount} shown · {meta.withDataCount} of {meta.scannedCount}{' '}
            companies have capex data
          </span>
        )}
      </Card>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-24 text-slate-400">
          <Loader2 className="animate-spin" size={18} />
          Loading investment data…
        </div>
      ) : error && items.length === 0 ? (
        <div className="py-24 text-center text-sm text-rose-400">
          Failed to load: {error}{' '}
          <button
            type="button"
            onClick={refetch}
            className="ml-2 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            Retry
          </button>
        </div>
      ) : noDataAtAll ? (
        <div className="mx-auto max-w-lg py-24 text-center text-sm text-slate-400">
          No investment data has been downloaded yet. Press{' '}
          <span className="text-slate-200">Refresh</span> in the top bar — capex
          figures are fetched together with the other company fundamentals, and
          the first run takes a few minutes.
        </div>
      ) : totalCount === 0 ? (
        <div className="py-24 text-center text-sm text-slate-400">
          No company matches these filters.
        </div>
      ) : (
        <>
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wider text-slate-500">
                  <SortHeader
                    label="Company"
                    col="ticker"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Sector"
                    col="sector"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    className="hidden lg:table-cell"
                  />
                  <SortHeader
                    label="Invested"
                    col="capex"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Money spent on property, plant, equipment and software over the last four reported quarters (or the latest full year when quarterly data is missing — marked FY). Shown in the company's own reporting currency, which is not always PLN."
                    className="text-right"
                  />
                  <SortHeader
                    label="vs last year"
                    col="capexGrowthYoyPct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Change in yearly investment: the latest full year against the year before it. Rising capex usually means expansion, falling capex belt-tightening — neither is automatically good or bad."
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="% of revenue"
                    col="capexToRevenuePct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Capex as a share of revenue — capital intensity. This is the fair way to compare a small heavy investor with a large light one. Heavy industry and utilities run high; software and retail run low."
                    className="text-right"
                  />
                  <SortHeader
                    label="% of cash flow"
                    col="capexToOcfPct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Capex as a share of the cash the business itself generated. Above 100% the company is investing more than it earned in cash, so the difference comes from reserves or debt."
                    className="hidden text-right sm:table-cell"
                  />
                  <SortHeader
                    label="Cash flow"
                    col="operatingCashFlow"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Operating cash flow over the same period: the cash the business generated before investing."
                    className="hidden text-right lg:table-cell"
                  />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <CapexRow
                    key={item.ticker}
                    item={item}
                    onOpen={() => navigate(`/stock/${item.ticker.toLowerCase()}`)}
                  />
                ))}
              </tbody>
            </table>
          </Card>

          {/* Infinite-scroll footer */}
          <div className="flex flex-col items-center gap-3 pb-2">
            <span className="text-xs text-slate-500">
              Showing {items.length} of {totalCount} companies
            </span>

            {/* Sentinel: scrolling this into view loads the next page. */}
            <div ref={sentinelRef} className="h-px w-full" />

            {loadingMore && (
              <span className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 className="animate-spin" size={14} />
                Loading more…
              </span>
            )}

            {error && items.length > 0 && !loadingMore && (
              <span className="text-xs text-rose-400">
                Couldn’t load more: {error}{' '}
                <button
                  type="button"
                  onClick={refetch}
                  className="ml-1 rounded-md border border-slate-700 px-2 py-0.5 text-slate-300 hover:bg-slate-800"
                >
                  Retry
                </button>
              </span>
            )}

            {!hasMore && !loadingMore && !error && (
              <span className="text-xs text-slate-600">End of results</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function CapexRow({ item, onOpen }: { item: ApiCapexItem; onOpen: () => void }) {
  return (
    <tr
      onClick={onOpen}
      className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/40"
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2.5">
          <TickerMark ticker={item.ticker} />
          <div className="min-w-0">
            <div className="font-semibold text-slate-100">{item.ticker}</div>
            <div className="max-w-[180px] truncate text-xs text-slate-500">
              {item.name}
            </div>
          </div>
        </div>
      </td>
      <td className="hidden px-4 py-3 text-xs text-slate-400 lg:table-cell">
        {item.sector ?? '—'}
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-slate-200">
        {item.capex == null ? (
          <Blank />
        ) : (
          <>
            {fmtMoney(item.capex, item.currency)}
            {/* The headline figure is a full year, not the last 12 months —
                say so rather than letting the two look identical. */}
            {item.basis === 'annual' && (
              <span className="ml-1 text-[10px] uppercase text-slate-500">FY</span>
            )}
          </>
        )}
      </td>
      <td className="hidden px-4 py-3 text-right text-sm tabular-nums md:table-cell">
        {item.capexGrowthYoyPct == null ? (
          <Blank />
        ) : (
          <span className={deltaTone(item.capexGrowthYoyPct)}>
            {fmtPct(item.capexGrowthYoyPct)}
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-sm tabular-nums text-slate-200">
        {item.capexToRevenuePct == null ? (
          <Blank />
        ) : (
          `${item.capexToRevenuePct.toFixed(1)}%`
        )}
      </td>
      <td
        className={
          'hidden px-4 py-3 text-right text-sm tabular-nums sm:table-cell ' +
          ocfTone(item.capexToOcfPct)
        }
      >
        {item.capexToOcfPct == null ? <Blank /> : `${item.capexToOcfPct.toFixed(0)}%`}
      </td>
      <td className="hidden px-4 py-3 text-right text-sm tabular-nums text-slate-400 lg:table-cell">
        {item.operatingCashFlow == null ? (
          <Blank />
        ) : (
          fmtMoney(item.operatingCashFlow, item.currency)
        )}
      </td>
    </tr>
  )
}
