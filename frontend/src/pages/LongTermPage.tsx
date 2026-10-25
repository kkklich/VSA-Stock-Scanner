import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CompanyLink } from '../components/ui'
import { MarketTabs } from '../components/MarketTabs'
import { LoadError, LongTermHistory } from '../components/LongTermHistory'
import { LongTermFactorBar } from '../components/LongTermFactorBar'
import { scoreText } from '../lib/longTerm'
import { summarizeLongTermFreshness } from '../lib/longTermFreshness'
import { FAVORITES_KEY, loadFavorites } from '../lib/favorites'
import { ratingTone } from '../lib/format'
import { useSingleMarket } from '../hooks/useMarkets'
import { useLongTermRanking } from '../hooks/useLongTerm'
import { displayTicker, GPW_MARKET } from '../lib/markets'
import type { LongTermItem } from '../types/longTerm'

type SortKey = 'ticker' | 'score' | 'qualityScore' | 'valueScore' | 'momentumScore' | 'coverage'
const SORT_KEYS: SortKey[] = ['score', 'qualityScore', 'valueScore', 'momentumScore', 'coverage', 'ticker']
const SCORE_KEYS = ['score', 'qualityScore', 'valueScore', 'momentumScore'] as const
const UNKNOWN_SECTOR = '__unknown_sector__'

function loadedTime(value: string | null, locale: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? date.toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) : '—'
}

export function LongTermPage() {
  const { t, i18n } = useTranslation()
  const { market, markets, needsPicker, pick } = useSingleMarket()
  const { data, loading, error, refetch, lastUpdated, stale } = useLongTermRanking(market)
  const [query, setQuery] = useState('')
  const [scoredOnly, setScoredOnly] = useState(false)
  const [watchlistOnly, setWatchlistOnly] = useState(false)
  const [favorites, setFavorites] = useState(loadFavorites)
  const [sectorFilter, setSectorFilter] = useState<{ market: string | null; value: string }>({ market: null, value: '' })
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [ascending, setAscending] = useState(false)
  const [selected, setSelected] = useState<{ market: string; ticker: string } | null>(null)
  const historyButtons = useRef(new Map<string, HTMLButtonElement>())
  useEffect(() => {
    // Stars can change in another tab while this page remains open.
    const sync = () => setFavorites(loadFavorites())
    const onStorage = (event: StorageEvent) => { if (event.key === FAVORITES_KEY || event.key === null) sync() }
    window.addEventListener('storage', onStorage)
    window.addEventListener('focus', sync)
    return () => { window.removeEventListener('storage', onStorage); window.removeEventListener('focus', sync) }
  }, [])
  const sectors = useMemo(() => Array.from(new Set((data?.items ?? []).map((item) => item.sector?.trim() || UNKNOWN_SECTOR))).sort((a, b) => a.localeCompare(b, i18n.language)), [data, i18n.language])
  const sector = sectorFilter.market === market && sectors.includes(sectorFilter.value) ? sectorFilter.value : ''
  const freshness = useMemo(() => summarizeLongTermFreshness(data?.items ?? []), [data])
  const filtersActive = Boolean(query.trim() || scoredOnly || watchlistOnly || sector)
  function clearFilters() {
    setQuery('')
    setScoredOnly(false)
    setWatchlistOnly(false)
    setSectorFilter({ market, value: '' })
  }
  const items = useMemo(() => {
    const search = query.trim().toLocaleLowerCase()
    return (data?.items ?? []).filter((item) =>
      `${item.ticker} ${item.name}`.toLocaleLowerCase().includes(search)
      && (!scoredOnly || (item.eligible && item.score !== null))
      && (!watchlistOnly || favorites[item.ticker] === true)
      && (!sector || (item.sector?.trim() || UNKNOWN_SECTOR) === sector)
    ).sort((a, b) => {
      const left = a[sortKey], right = b[sortKey]
      // A missing figure always goes last, including ascending order.
      if (left == null) return right == null ? a.ticker.localeCompare(b.ticker) : 1
      if (right == null) return -1
      const delta = typeof left === 'string' && typeof right === 'string' ? left.localeCompare(right) : Number(left) - Number(right)
      return (ascending ? delta : -delta) || a.ticker.localeCompare(b.ticker)
    })
  }, [data, query, sortKey, ascending, scoredOnly, watchlistOnly, favorites, sector])
  const selectedItem = selected?.market === market ? data?.items.find((item) => item.ticker === selected.ticker) : undefined
  function selectItem(item: LongTermItem) {
    setSelected((previous) => previous?.ticker === item.ticker && previous.market === item.market ? null : { ticker: item.ticker, market: item.market })
  }
  function closeHistory(ticker: string) {
    setSelected(null)
    historyButtons.current.get(ticker)?.focus()
  }

  return <div className="space-y-4 p-4 md:p-6">
    <div>
      <h2 className="text-lg font-semibold text-slate-100">{t('longTerm.title')}</h2>
      <p className="mt-1 max-w-4xl text-sm leading-relaxed text-slate-400">{t('longTerm.shortDescription')}</p>
    </div>
    <details className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
      <summary className="cursor-pointer text-sm font-medium text-slate-300">{t('longTerm.howScoringWorks')}</summary>
      <div className="mt-3 space-y-3">
      <p className="text-sm leading-relaxed text-slate-400">{t('longTerm.description')}</p>
      <p className="text-sm text-slate-300">{t('longTerm.methodology')}</p>
      <div className="grid gap-3 md:grid-cols-3">
        {(['quality', 'value', 'momentum'] as const).map((factor) => <div key={factor} className="rounded-lg bg-slate-800/50 p-3">
          <h3 className="text-sm font-medium text-slate-100">{t(`longTerm.${factor}Score`)} · ⅓</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">{t(`longTerm.explanations.${factor}`)}</p>
        </div>)}
      </div>
      <p className="text-xs leading-relaxed text-slate-400">{t('longTerm.coverageExplanation')}</p>
      </div>
    </details>
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-3">
      {needsPicker && markets && <MarketTabs markets={markets} value={market ?? GPW_MARKET} onChange={pick} />}
      <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-slate-400 sm:flex-none">
        {t('longTerm.search')}
        <input value={query} onChange={(event) => setQuery(event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 sm:w-56" />
      </label>
      <label className="flex min-w-0 flex-col gap-1 text-xs text-slate-400">
        {t('longTerm.filters.sector')}
        <select value={sector} onChange={(event) => setSectorFilter({ market, value: event.target.value })} className="max-w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 sm:max-w-52">
          <option value="">{t('longTerm.filters.allSectors')}</option>
          {sectors.map((value) => <option key={value} value={value}>{value === UNKNOWN_SECTOR ? t('longTerm.filters.unknownSector') : value}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-400">
        {t('common.sortHeading')}
        <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200">
          {SORT_KEYS.map((key) => <option key={key} value={key}>{t(`longTerm.${key}`)}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => setAscending((value) => !value)} className="mt-4 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300">{t(ascending ? 'common.sortAsc' : 'common.sortDesc')} {ascending ? '↑' : '↓'}</button>
      <p className="text-xs text-slate-400 sm:ml-auto">{t('longTerm.oneMarket', { market: t(`markets.name.${market ?? GPW_MARKET}`, { defaultValue: market ?? 'GPW' }) })}</p>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-slate-800 pt-3 text-sm text-slate-300">
        <label className="flex items-center gap-2"><input type="checkbox" checked={scoredOnly} onChange={(event) => setScoredOnly(event.target.checked)} className="accent-emerald-500" />{t('longTerm.filters.scoredOnly')}</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={watchlistOnly} onChange={(event) => { setFavorites(loadFavorites()); setWatchlistOnly(event.target.checked) }} className="accent-emerald-500" />{t('longTerm.filters.watchlistOnly')}</label>
        {filtersActive && <button type="button" onClick={clearFilters} className="text-xs text-emerald-400 hover:underline">{t('longTerm.filters.clear')}</button>}
        {data && <p role="status" className="text-xs text-slate-400 sm:ml-auto">{t('longTerm.filters.matches', { count: items.length, total: data.items.length })}</p>}
      </div>
    </Card>
    {stale && data ? <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 p-3 text-sm text-amber-400">
      <p>{t('longTerm.freshness.stale')}</p>
      <button type="button" onClick={refetch} disabled={loading} className="underline disabled:opacity-50">{t(loading ? 'longTerm.freshness.reloading' : 'common.retry')}</button>
    </div> : error && <LoadError retry={refetch} />}
    {(loading || market === null) && !data && <p role="status" className="text-sm text-slate-400">{t('common.loading')}</p>}
    {data && <>
      {!data.dbEnabled && <p className="rounded-lg border border-amber-500/30 p-3 text-sm text-amber-400">{t('longTerm.storageUnavailable')}</p>}
      <section aria-label={t('longTerm.freshness.label')} className="rounded-lg border border-slate-800 px-4 py-3 text-xs text-slate-400">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <dl className="flex flex-wrap gap-x-6 gap-y-2">
            <div><dt>{t('longTerm.freshness.lastLoaded')}</dt><dd className="mt-1 text-slate-200">{loadedTime(lastUpdated, i18n.language)}</dd></div>
            <div><dt>{t('longTerm.latestSession')}</dt><dd className="mt-1 text-slate-200">{freshness.latestPriceSession ?? data.asOf ?? '—'}</dd></div>
            <div><dt>{t('longTerm.freshness.financials')}</dt><dd className="mt-1 text-slate-200">{loadedTime(freshness.oldestFinancialObservation, i18n.language)}{freshness.newestFinancialObservation !== freshness.oldestFinancialObservation && <> – {loadedTime(freshness.newestFinancialObservation, i18n.language)}</>}</dd></div>
          </dl>
          <button type="button" onClick={refetch} disabled={loading} className="rounded-lg border border-slate-700 px-3 py-2 text-slate-300 disabled:opacity-50">{t(loading ? 'longTerm.freshness.reloading' : 'longTerm.freshness.reload')}</button>
        </div>
        <p className="mt-2">{t('longTerm.freshness.explanation')}</p>
        {(freshness.missingFinancialCount > 0 || freshness.staleFinancialCount > 0) && <p className="mt-1 text-amber-400">{t('longTerm.freshness.issues', { missing: freshness.missingFinancialCount, stale: freshness.staleFinancialCount })}</p>}
      </section>
      <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-400">
        <p>{t('longTerm.counts', { scored: data.scoredCount, total: data.totalCount })}</p>
        <p>{t('longTerm.modelVersion')}: {data.modelVersion}</p>
      </div>
      {data.items.length > 0 && data.scoredCount === 0 && <p className="text-sm text-amber-400">{t('longTerm.noneScored')}</p>}
      <Card className="overflow-hidden">
        <div className="lg:overflow-x-auto">
          {/* The same semantic rows reflow into cards below lg, including the
              expanded history. Do not duplicate history components: that would
              fetch every selected stock twice and create duplicate regions. */}
          <table className="block w-full text-left text-sm lg:table lg:min-w-[780px]" aria-label={t('longTerm.title')}>
            <thead className="hidden border-b border-slate-800 bg-slate-800/30 text-xs text-slate-400 lg:table-header-group"><tr>
              <th scope="col" className="px-4 py-3">{t('longTerm.ticker')}</th>
              {SCORE_KEYS.map((key) => <th scope="col" key={key} className="px-3 py-3 text-right" aria-sort={sortKey === key ? (ascending ? 'ascending' : 'descending') : 'none'}>
                <button type="button" onClick={() => { if (sortKey === key) setAscending(!ascending); else { setSortKey(key); setAscending(false) } }}>{t(`longTerm.${key}`)}{sortKey === key ? (ascending ? ' ↑' : ' ↓') : ''}</button>
              </th>)}
              <th scope="col" className="px-3 py-3 text-right">{t('longTerm.coverage')}</th>
              <th scope="col" className="px-4 py-3">{t('longTerm.status')}</th>
            </tr></thead>
            <tbody className="block space-y-3 p-3 lg:table-row-group lg:divide-y lg:divide-slate-800/70 lg:space-y-0 lg:p-0">{items.map((item) => <Fragment key={item.ticker}><tr className={`grid grid-cols-4 rounded-lg border border-slate-800 lg:table-row lg:rounded-none lg:border-0 ${selectedItem?.ticker === item.ticker ? 'bg-slate-800/50' : 'hover:bg-slate-800/20'}`}>
              <td className="col-span-4 block min-w-0 px-4 py-3 lg:table-cell lg:max-w-64">
                <CompanyLink ticker={item.ticker} className="font-semibold text-slate-100">{displayTicker(item.ticker).toUpperCase()}</CompanyLink>
                <p className="truncate text-xs text-slate-400" title={item.name}>{item.name}</p>
                <p className="mt-1 text-[11px] text-slate-500">{t('longTerm.session')}: {item.asOf ?? '—'}</p>
              </td>
              {SCORE_KEYS.map((key) => <td key={key} className={`block min-w-0 px-2 py-3 tabular-nums lg:table-cell lg:px-3 lg:text-right ${item[key] === null ? 'text-slate-500' : key === 'score' ? `font-semibold ${ratingTone(item[key]).text}` : 'text-slate-300'}`}>
                <span className="mb-1 block min-h-8 break-words text-[10px] font-normal leading-4 text-slate-400 lg:hidden">{t(`longTerm.${key}`)}</span>
                {key === 'score' ? scoreText(item[key], i18n.language) : <LongTermFactorBar value={item[key]} label={t(`longTerm.${key}`)} />}
              </td>)}
              <td className="block min-w-0 px-3 py-3 text-slate-300 lg:table-cell lg:text-right"><span className="mb-1 block text-[11px] text-slate-400 lg:hidden">{t('longTerm.coverage')}</span>{scoreText(item.coverage, i18n.language)}%</td>
              <td className="col-span-3 block min-w-0 px-4 py-3 text-xs lg:table-cell lg:max-w-64">
                <p className={item.eligible ? 'text-slate-400' : 'text-amber-400'}>{item.eligible ? t('longTerm.scored') : t('longTerm.unscored')}</p>
                {item.missing.length > 0 && <p className="mt-1 text-slate-400">{item.missing.map((key) => t(`longTerm.missing.${key}`, { defaultValue: t('longTerm.missing.unknown') })).join(' · ')}</p>}
                <button ref={(button) => { if (button) historyButtons.current.set(item.ticker, button); else historyButtons.current.delete(item.ticker) }} type="button" aria-expanded={selectedItem?.ticker === item.ticker} aria-controls={selectedItem?.ticker === item.ticker ? `long-term-history-${item.ticker}` : undefined} onClick={() => selectItem(item)} className="mt-2 text-emerald-400 hover:underline" aria-label={t('longTerm.openHistory', { ticker: displayTicker(item.ticker).toUpperCase() })}>{t('longTerm.history')}</button>
              </td>
            </tr>{selectedItem?.ticker === item.ticker && <tr className="block lg:table-row"><td colSpan={7} className="block min-w-0 lg:table-cell lg:p-3"><div id={`long-term-history-${item.ticker}`}><LongTermHistory item={item} close={() => closeHistory(item.ticker)} /></div></td></tr>}</Fragment>)}</tbody>
          </table>
        </div>
        {items.length === 0 && <p className="p-6 text-center text-sm text-slate-400">{t(data.items.length ? 'longTerm.noMatches' : 'longTerm.empty')}</p>}
      </Card>
    </>}
  </div>
}
