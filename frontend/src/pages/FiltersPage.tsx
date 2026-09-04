// Filters page — a full stock screener over the VSA ranking with saved
// presets. All criteria are applied server-side by GET /api/stocks/ranking
// (sector, rating band, signal + recency, price range, liquidity); a named
// combination can be saved as a preset (localStorage) and re-run in one click.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookmarkPlus, Loader2, RotateCcw, X } from 'lucide-react'
import {
  Card,
  CompanyLink,
  InfoTip,
  Pagination,
  RatingMeter,
  SignalBadge,
  SortHeader,
  TickerMark,
} from '../components/ui'
import { useRanking, type RankingParams } from '../hooks/useRanking'
import { useCompanies } from '../hooks/useCompanies'
import type { RankingSortKey, SortDir } from '../api/stocksApi'
import type { SignalVerdict } from '../types'
import { deltaTone, fmtPct, fmtPrice } from '../lib/format'
import { SIGNAL_OPTIONS } from '../lib/filterOptions'
import {
  EMPTY_FILTERS,
  NEAR_52W_PCT,
  createPreset,
  filtersActive,
  loadPresets,
  range52wParams,
  savePresets,
  type FilterPreset,
  type Range52w,
  type ScreenFilters,
} from '../lib/filterPresets'

const PAGE_SIZE = 25

/** Columns that read naturally A→Z on the first click. */
const TEXT_COLUMNS: RankingSortKey[] = ['ticker', 'name', 'sector']

const RECENCY_OPTIONS = [
  { value: null, label: 'Any time' },
  { value: 3, label: '≤ 3 days' },
  { value: 5, label: '≤ 5 days' },
  { value: 10, label: '≤ 10 days' },
  { value: 20, label: '≤ 20 days' },
] as const

const VOLUME_OPTIONS = [
  { value: null, label: 'Any' },
  { value: 10_000, label: '≥ 10k' },
  { value: 50_000, label: '≥ 50k' },
  { value: 100_000, label: '≥ 100k' },
  { value: 500_000, label: '≥ 500k' },
] as const

const RANGE_52W_OPTIONS: { value: Range52w; label: string }[] = [
  { value: 'any', label: 'Anywhere' },
  { value: 'newHigh', label: 'New 52-week high' },
  { value: 'nearHigh', label: `Within ${NEAR_52W_PCT}% of high` },
  { value: 'nearLow', label: `Within ${NEAR_52W_PCT}% of low` },
  { value: 'newLow', label: 'New 52-week low' },
]

const inputClass =
  'w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none'

/** Labelled wrapper so every control lines up in the filter grid. */
function Field({
  label,
  info,
  children,
}: {
  label: string
  info?: string
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
        {info && <InfoTip text={info} />}
      </span>
      {children}
    </label>
  )
}

/**
 * One 52-week distance cell: the percentage plus a "NEW" chip when the latest
 * session actually set the extreme (a breakout/breakdown, not just proximity).
 */
function Range52wCell({
  pct,
  isNew,
  newLabel,
  newTone,
}: {
  pct: number | null
  isNew: boolean
  newLabel: string
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
          {newLabel}
        </span>
      )}
      <span className="tabular-nums text-slate-300">{fmtPct(pct)}</span>
    </span>
  )
}

/** Parse a number input's value; empty/invalid → null (no filter). */
function numOrNull(raw: string): number | null {
  if (raw.trim() === '') return null
  const n = Number(raw)
  return Number.isFinite(n) && n >= 0 ? n : null
}

export function FiltersPage() {
  const navigate = useNavigate()

  const [filters, setFilters] = useState<ScreenFilters>(EMPTY_FILTERS)
  // Debounced copy — typing in the text/number inputs shouldn't fire a
  // request per keystroke.
  const [applied, setApplied] = useState<ScreenFilters>(EMPTY_FILTERS)
  const [sortBy, setSortBy] = useState<RankingSortKey>('currentRating')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)

  // Saved presets (localStorage) + the "save as…" inline form.
  const [presets, setPresets] = useState<FilterPreset[]>(loadPresets)
  const [saving, setSaving] = useState(false)
  const [presetName, setPresetName] = useState('')
  // Preset the current filter values came from (highlight its chip).
  const [activePresetId, setActivePresetId] = useState<string | null>(null)

  useEffect(() => {
    savePresets(presets)
  }, [presets])

  useEffect(() => {
    const t = setTimeout(() => setApplied(filters), 300)
    return () => clearTimeout(t)
  }, [filters])

  // Back to page 1 whenever the effective query changes.
  useEffect(() => {
    setPage(1)
  }, [applied, sortBy, sortDir])

  const set = <K extends keyof ScreenFilters>(key: K, value: ScreenFilters[K]) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setActivePresetId(null)
  }

  // Distinct sectors from the tracked-companies list, alphabetical.
  const { companies } = useCompanies()
  const sectors = useMemo(() => {
    const set = new Set<string>()
    for (const c of companies) if (c.sector) set.add(c.sector)
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [companies])

  const rankingParams = useMemo<RankingParams>(
    () => ({
      page,
      pageSize: PAGE_SIZE,
      sortBy,
      sortDir,
      q: applied.q.trim() || undefined,
      minRating: applied.minRating || undefined,
      maxRating: applied.maxRating < 100 ? applied.maxRating : undefined,
      signal: applied.signal,
      sector: applied.sector !== 'all' ? applied.sector : undefined,
      maxDaysSinceSignal: applied.maxDaysSinceSignal ?? undefined,
      minPrice: applied.minPrice ?? undefined,
      maxPrice: applied.maxPrice ?? undefined,
      minVolume: applied.minVolume ?? undefined,
      ...range52wParams(applied.range52w),
      weeklyConfirms: applied.weeklyConfirms || undefined,
    }),
    [page, sortBy, sortDir, applied],
  )

  const { data, total, loading, error, refetch } = useRanking(rankingParams)
  const rows = data ?? []
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const anyActive = filtersActive(filters)

  const onSort = (col: RankingSortKey) => {
    if (col === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(col)
      setSortDir(TEXT_COLUMNS.includes(col) ? 'asc' : 'desc')
    }
  }

  const applyPreset = (preset: FilterPreset) => {
    setFilters({ ...preset.filters })
    setActivePresetId(preset.id)
  }

  const deletePreset = (id: string) => {
    setPresets((p) => p.filter((x) => x.id !== id))
    if (activePresetId === id) setActivePresetId(null)
  }

  const saveCurrentPreset = () => {
    const name = presetName.trim()
    if (!name) return
    const preset = createPreset(name, filters)
    setPresets((p) => [...p, preset])
    setActivePresetId(preset.id)
    setPresetName('')
    setSaving(false)
  }

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS)
    setActivePresetId(null)
  }

  return (
    <div className="space-y-4 p-4 md:p-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold text-slate-100">
          Filters — screen the GPW your way
        </h2>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-400">
          Combine sector, VSA rating, signal, price and liquidity criteria to
          screen every tracked stock. Save a combination as a preset to re-run
          it with one click.
        </p>
      </div>

      {/* Saved presets */}
      <Card className="flex flex-wrap items-center gap-2 px-4 py-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Presets
        </span>
        {presets.length === 0 && !saving && (
          <span className="text-xs text-slate-500">
            None saved yet — set some filters below, then “Save preset”.
          </span>
        )}
        {presets.map((p) => (
          <span
            key={p.id}
            className={
              'inline-flex items-center overflow-hidden rounded-lg border text-xs transition-colors ' +
              (p.id === activePresetId
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                : 'border-slate-700 bg-slate-900 text-slate-300')
            }
          >
            <button
              type="button"
              onClick={() => applyPreset(p)}
              className="px-2.5 py-1.5 font-medium hover:bg-slate-800"
              title={`Apply preset "${p.name}"`}
            >
              {p.name}
            </button>
            <button
              type="button"
              onClick={() => deletePreset(p.id)}
              className="border-l border-slate-700/60 px-1.5 py-1.5 text-slate-500 hover:bg-rose-500/10 hover:text-rose-400"
              aria-label={`Delete preset "${p.name}"`}
              title="Delete preset"
            >
              <X size={12} />
            </button>
          </span>
        ))}

        <span className="ml-auto flex items-center gap-2">
          {saving ? (
            <>
              <input
                autoFocus
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveCurrentPreset()
                  if (e.key === 'Escape') setSaving(false)
                }}
                placeholder="Preset name…"
                className="w-44 rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none"
              />
              <button
                type="button"
                onClick={saveCurrentPreset}
                disabled={!presetName.trim()}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => setSaving(false)}
                className="rounded-lg border border-slate-800 px-2 py-1.5 text-xs text-slate-400 hover:bg-slate-800"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setSaving(true)}
              disabled={!anyActive}
              title={
                anyActive
                  ? 'Save the current filters as a preset'
                  : 'Set at least one filter first'
              }
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <BookmarkPlus size={13} /> Save preset
            </button>
          )}
        </span>
      </Card>

      {/* Filter controls */}
      <Card className="px-4 py-4">
        <div className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          <Field label="Search">
            <input
              value={filters.q}
              onChange={(e) => set('q', e.target.value)}
              placeholder="Ticker or name…"
              className={inputClass}
            />
          </Field>

          <Field label="Sector">
            <select
              value={filters.sector}
              onChange={(e) => set('sector', e.target.value)}
              className={inputClass}
            >
              <option value="all">All sectors</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Signal"
            info="Verdict from the most recent VSA pattern: Spring / SOS → Strong Buy, Successful Test → Buy, No Demand → Sell, Upthrust / SOW → Strong Sell."
          >
            <select
              value={filters.signal}
              onChange={(e) => set('signal', e.target.value as SignalVerdict | 'all')}
              className={inputClass}
            >
              {SIGNAL_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === 'all' ? 'All signals' : s}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Signal age"
            info="Only stocks whose last VSA pattern fired within this many sessions. Fresh signals matter most in VSA — old ones fade."
          >
            <select
              value={filters.maxDaysSinceSignal ?? ''}
              onChange={(e) =>
                set(
                  'maxDaysSinceSignal',
                  e.target.value === '' ? null : Number(e.target.value),
                )
              }
              className={inputClass}
            >
              {RECENCY_OPTIONS.map((o) => (
                <option key={o.label} value={o.value ?? ''}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="52-week range"
            info="Where the last close sits between the 52-week low and high. Breakouts to new highs and stocks scraping their lows are the classic screens; VSA reads a new high on heavy volume as possible distribution, not automatic strength."
          >
            <select
              value={filters.range52w}
              onChange={(e) => set('range52w', e.target.value as Range52w)}
              className={inputClass}
            >
              {RANGE_52W_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Weekly timeframe"
            info="Multi-timeframe confirmation. The stored daily bars are resampled into weekly candles and run through the same VSA engine; 'Confirms daily' keeps only stocks whose weekly verdict leans the same way as the daily one (both bullish, or both bearish). VSA traders treat a daily signal the weekly chart agrees with as far more reliable. Stocks with under ~30 weeks of stored history have no weekly reading and are excluded by this filter."
          >
            <select
              value={filters.weeklyConfirms ? 'confirms' : 'any'}
              onChange={(e) => set('weeklyConfirms', e.target.value === 'confirms')}
              className={inputClass}
            >
              <option value="any">Any</option>
              <option value="confirms">Confirms daily</option>
            </select>
          </Field>

          <Field
            label="Min. volume"
            info="20-session median volume (shares) — a liquidity floor so thinly traded stocks are excluded."
          >
            <select
              value={filters.minVolume ?? ''}
              onChange={(e) =>
                set('minVolume', e.target.value === '' ? null : Number(e.target.value))
              }
              className={inputClass}
            >
              {VOLUME_OPTIONS.map((o) => (
                <option key={o.label} value={o.value ?? ''}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Rating from"
            info="Lower bound of the VSA rating band (0–100). Above 70 = strong accumulation."
          >
            <input
              type="number"
              min={0}
              max={100}
              value={filters.minRating || ''}
              onChange={(e) =>
                set('minRating', Math.min(100, Math.max(0, numOrNull(e.target.value) ?? 0)))
              }
              placeholder="0"
              className={inputClass}
            />
          </Field>

          <Field
            label="Rating to"
            info="Upper bound of the VSA rating band. Below 30 = distribution (weakness) — useful for finding short candidates."
          >
            <input
              type="number"
              min={0}
              max={100}
              value={filters.maxRating < 100 ? filters.maxRating : ''}
              onChange={(e) =>
                set(
                  'maxRating',
                  Math.min(100, Math.max(0, numOrNull(e.target.value) ?? 100)),
                )
              }
              placeholder="100"
              className={inputClass}
            />
          </Field>

          <Field label="Price from (PLN)">
            <input
              type="number"
              min={0}
              step="0.01"
              value={filters.minPrice ?? ''}
              onChange={(e) => set('minPrice', numOrNull(e.target.value))}
              placeholder="Any"
              className={inputClass}
            />
          </Field>

          <Field label="Price to (PLN)">
            <input
              type="number"
              min={0}
              step="0.01"
              value={filters.maxPrice ?? ''}
              onChange={(e) => set('maxPrice', numOrNull(e.target.value))}
              placeholder="Any"
              className={inputClass}
            />
          </Field>

          <div className="flex items-end">
            <button
              type="button"
              onClick={clearFilters}
              disabled={!anyActive}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw size={14} /> Clear all
            </button>
          </div>
        </div>
      </Card>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-24 text-slate-400">
          <Loader2 className="animate-spin" size={18} />
          Screening the GPW…
        </div>
      ) : error ? (
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
      ) : total === 0 ? (
        <div className="py-24 text-center text-sm text-slate-400">
          No stocks match these criteria.{' '}
          <button
            type="button"
            onClick={clearFilters}
            className="text-emerald-400 hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          {/* ── Desktop table (lg+) ─────────────────────────────────────────
              min-width (not an overflow wrapper) so the sticky header can pin to
              the page as you scroll; the table stays inside the card and the
              page scrolls sideways when the viewport is narrower than it. Below
              lg the table is hidden and the card list (further down) is shown,
              so phones and tablets never scroll sideways. */}
          <Card className="hidden min-w-[1000px] lg:block">
            <table className="w-full min-w-[1000px] text-left text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-slate-500">
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
                    label="Price"
                    col="lastPrice"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    className="text-right"
                  />
                  <SortHeader
                    label="Change"
                    col="priceChangePct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    className="text-right"
                  />
                  <SortHeader
                    label="From 52w high"
                    col="distFrom52wHighPct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="How far below the 52-week high the last close sits. 0% means it closed at the high; a “NEW” chip marks a session that set a fresh 52-week high."
                    className="hidden text-right md:table-cell"
                  />
                  <SortHeader
                    label="From 52w low"
                    col="distFrom52wLowPct"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="How far above the 52-week low the last close sits. A “NEW” chip marks a session that set a fresh 52-week low."
                    className="hidden text-right xl:table-cell"
                  />
                  <SortHeader
                    label="Rating (0–100)"
                    col="currentRating"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    info="VSA score with time decay: recent bullish signals push it above 50, bearish ones below."
                  />
                  <SortHeader
                    label="Signal"
                    col="lastSignal"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                  />
                  <SortHeader
                    label="Days ago"
                    col="daysSinceSignal"
                    sortBy={sortBy}
                    sortDir={sortDir}
                    onSort={onSort}
                    align="right"
                    info="Sessions since the last VSA pattern fired."
                    className="hidden text-right md:table-cell"
                  />
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr
                    key={s.ticker}
                    onClick={() => navigate(`/stock/${s.ticker.toLowerCase()}`)}
                    className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/40"
                  >
                    <td className="px-4 py-3">
                      <CompanyLink
                        ticker={s.ticker}
                        title={s.name}
                        className="flex items-center gap-2.5"
                      >
                        <TickerMark ticker={s.ticker} />
                        <div className="min-w-0">
                          <div className="font-semibold text-slate-100">
                            {s.ticker}
                          </div>
                          <div className="max-w-[200px] truncate text-xs text-slate-500">
                            {s.name}
                          </div>
                        </div>
                      </CompanyLink>
                    </td>
                    <td className="hidden px-4 py-3 text-xs text-slate-400 lg:table-cell">
                      {s.sector ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm tabular-nums text-slate-200">
                      {fmtPrice(s.lastPrice)}
                    </td>
                    <td
                      className={
                        'px-4 py-3 text-right text-sm font-medium tabular-nums ' +
                        deltaTone(s.priceChangePct)
                      }
                    >
                      {fmtPct(s.priceChangePct)}
                    </td>
                    <td className="hidden px-4 py-3 text-right text-sm md:table-cell">
                      <Range52wCell
                        pct={s.distFrom52wHighPct}
                        isNew={s.isNew52wHigh}
                        newLabel="new"
                        newTone="bg-emerald-500/15 text-emerald-400 ring-emerald-500/30"
                      />
                    </td>
                    <td className="hidden px-4 py-3 text-right text-sm xl:table-cell">
                      <Range52wCell
                        pct={s.distFrom52wLowPct}
                        isNew={s.isNew52wLow}
                        newLabel="new"
                        newTone="bg-rose-500/15 text-rose-400 ring-rose-500/30"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <RatingMeter rating={s.currentRating} />
                    </td>
                    <td className="px-4 py-3">
                      <SignalBadge verdict={s.lastSignal} />
                    </td>
                    <td className="hidden px-4 py-3 text-right text-xs tabular-nums text-slate-400 md:table-cell">
                      {s.daysSinceSignal === 999 ? '—' : s.daysSinceSignal}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* ── Mobile / tablet cards (below lg) ─────────────────────────── */}
          <div className="space-y-2.5 lg:hidden">
            {rows.map((s) => (
              <div
                key={s.ticker}
                onClick={() => navigate(`/stock/${s.ticker.toLowerCase()}`)}
                role="button"
                tabIndex={0}
                aria-label={`${s.ticker} ${s.name}, open details`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    navigate(`/stock/${s.ticker.toLowerCase()}`)
                  }
                }}
                className="cursor-pointer rounded-xl border border-slate-800 bg-slate-900/40 p-4 transition-colors hover:bg-slate-800/40 focus:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-emerald-500/50"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2.5">
                    <TickerMark ticker={s.ticker} />
                    <div className="min-w-0">
                      <div className="font-semibold text-slate-100">{s.ticker}</div>
                      <div className="truncate text-xs text-slate-500">{s.name}</div>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="font-medium tabular-nums text-slate-200">
                      {fmtPrice(s.lastPrice)} PLN
                    </div>
                    <div
                      className={
                        'text-xs tabular-nums ' + deltaTone(s.priceChangePct)
                      }
                    >
                      {fmtPct(s.priceChangePct)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between gap-3">
                  <RatingMeter rating={s.currentRating} />
                  <SignalBadge verdict={s.lastSignal} />
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/60 pt-2 text-xs text-slate-500">
                  <span className="min-w-0 truncate">{s.sector ?? '—'}</span>
                  <span>
                    {s.daysSinceSignal === 999
                      ? 'No recent signal'
                      : `${s.daysSinceSignal} ${s.daysSinceSignal === 1 ? 'day' : 'days'} ago`}
                  </span>
                  <span className="ml-auto flex items-center gap-1">
                    52w high
                    <Range52wCell
                      pct={s.distFrom52wHighPct}
                      isNew={s.isNew52wHigh}
                      newLabel="new"
                      newTone="bg-emerald-500/15 text-emerald-400 ring-emerald-500/30"
                    />
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Pager */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-2">
            <span className="text-xs text-slate-500">
              Showing {(page - 1) * PAGE_SIZE + 1}–
              {Math.min(page * PAGE_SIZE, total)} of {total} matching stocks
            </span>
            {totalPages > 1 && (
              <Pagination current={page} total={totalPages} onChange={setPage} />
            )}
          </div>
        </>
      )}
    </div>
  )
}
