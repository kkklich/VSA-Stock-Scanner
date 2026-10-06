// Typed API calls for the /api/stocks/* endpoints.
// Shapes mirror the Pydantic models in backend-python/app/models/stocks.py.
//
// All analysis endpoints accept an optional `settings` value (JSON string from
// lib/vsaSettings.ts) so the user's Scanner configuration drives the actual
// VSA calculation on the backend.

import { apiFetch, apiFetchWithHeaders } from './client'
import { serializeSort, type SortDir, type SortLevel } from '../lib/sorting'
import type { Candle, SignalVerdict, VsaSignal } from '../types'

// Re-exported so a page can take the whole payload's vocabulary from this one
// module (ChartsPage imports SignalVerdict alongside ChartInterval; the sort
// types live in lib/sorting.ts, which owns the multi-column sorting rules).
export type { SignalVerdict, SortDir, SortLevel }

// ── GET /api/stocks/markets (the markets this deployment serves) ─────────────

export interface ApiMarketIndex {
  id: string
  name: string
}

export interface ApiMarket {
  /** "gpw", "us", "de", "fr", "nl", "uk". */
  id: string
  name: string
  shortName: string
  country: string
  region: 'poland' | 'europe' | 'usa'
  exchange: string
  /** The currency most prices are quoted in ("GBp" = pence). */
  currency: string
  /** The currency whole amounts are stated in ("GBP" for a pence market). */
  majorCurrency: string
  timezone: string
  /** What the app appends to a symbol on this market ("" for the GPW). */
  tickerSuffix: string
  /** Which nightly run refreshes it: "europe" or "us". */
  refreshRun: string
  companyCount: number
  indices: ApiMarketIndex[]
}

export async function fetchMarkets(): Promise<ApiMarket[]> {
  return apiFetch<ApiMarket[]>('/api/stocks/markets')
}

// ── GET /api/stocks (tracked companies) ───────────────────────────────────────

export interface ApiCompany {
  /** "kgh" on the GPW; suffixed elsewhere ("aapl.us"). */
  ticker: string
  name: string
  sector: string | null
  /** Market id; absent from older backends (then: the GPW). */
  market?: string
  exchange?: string | null
  currency?: string | null
}

/** Companies of one market, or of every served market (the default). */
export async function fetchCompanies(market: string = 'all'): Promise<ApiCompany[]> {
  return apiFetch<ApiCompany[]>(`/api/stocks?market=${encodeURIComponent(market)}`)
}

// ── GET /api/stocks/ranking ───────────────────────────────────────────────────

/** One trading method's read of one stock (a cell in the multi-method list). */
export interface ApiMethodResult {
  methodId: string
  /** 0–100 attractiveness for this method (feeds the combined score). */
  score: number
  /** Age in days of the last bar the setup fired on; 999 = not recently. */
  daysSince: number
  /** The setup fired on the most recent bar. */
  fired: boolean
  /** Short human note, e.g. the VSA verdict or "6/7 rules". */
  detail: string | null
  /** False when the stock has too little history to evaluate this method. */
  available: boolean
}

export interface ApiRankingItem {
  ticker: string
  name: string
  /** The market the stock trades on ("gpw", "us", …); absent = the GPW. */
  market?: string
  /** The currency its prices are in, as Yahoo writes it ("PLN", "GBp"…); absent = PLN. */
  currency?: string
  /**
   * The session (YYYY-MM-DD) every figure on this row describes. Markets close
   * hours apart — Europe in the late Warsaw afternoon, the US at ~22:15 Warsaw
   * time — so a pooled list can legitimately carry today's European rows
   * beside yesterday's American ones. Absent on an older backend.
   */
  lastSession?: string | null
  lastPrice: number
  priceChangePct: number
  currentRating: number
  ratingChange: number
  lastSignal: SignalVerdict
  daysSinceSignal: number
  sparkline: number[]
  volume: number
  sector: string | null
  aiConfidence: number
  /** % below the 52-week high (≤ 0; 0 = closed at the high). */
  distFrom52wHighPct: number | null
  /** % above the 52-week low (≥ 0). */
  distFrom52wLowPct: number | null
  /** The latest session set a new 52-week high / low. */
  isNew52wHigh: boolean
  isNew52wLow: boolean
  /** Per-method results keyed by method id (VSA + any registered method). */
  methodResults: Record<string, ApiMethodResult>
  /** Mean of the selected methods' scores (0–100), or null. */
  combinedScore: number | null
  /** Weekly (multi-timeframe) VSA rating 0–100; null when history too short. */
  weeklyRating: number | null
  /** Weekly VSA verdict badge; null when history too short. */
  weeklySignal: SignalVerdict | null
  /** How the weekly timeframe relates to the daily verdict; null when history too short. */
  weeklyAgreement: WeeklyAgreement | null
  /**
   * Today's session so far, while the stock's exchange is trading and the
   * day's final bar is not stored yet. When present, `lastPrice`,
   * `priceChangePct` and the last sparkline point are its figures — every
   * rating, signal and method score is still the last FINISHED session's
   * (`lastSession`). Absent (null) otherwise, and on older backends.
   */
  live?: ApiLivePrice | null
}

/**
 * Today's session so far for one stock, downloaded every hour while its
 * exchange trades (backend `app/services/live_prices.py`). Shown beside the
 * analysis, never part of it: an unfinished day has only part of its volume,
 * and VSA reads low volume as a signal.
 */
export interface ApiLivePrice {
  /** The trading day in progress, YYYY-MM-DD on the exchange's calendar. */
  sessionDate: string
  /** Latest price and today's range so far, in the stock's own currency. */
  price: number
  open: number
  high: number
  low: number
  /** Shares traded so far today; 0 = no trade yet today. Null when unknown. */
  volume: number | null
  previousClose: number | null
  /** Today's change so far against the previous close, percent. */
  changePct: number | null
  /** When that price was traded (ISO, UTC) — quotes can be delayed ~15 min. */
  asOf: string
  /** When the app downloaded it (ISO, UTC) — the hourly run. */
  fetchedAt: string
}

/** How the weekly VSA verdict relates to the daily one. */
export type WeeklyAgreement = 'confirms' | 'conflicts' | 'neutral'

/** Catalogue entry for one selectable trading method. */
export interface ApiTradingMethod {
  id: string
  name: string
  description: string
  source: string
  sourceUrl: string | null
  direction: string
}

/** GET /api/stocks/methods — the trading-method catalogue for the selector. */
export async function fetchMethods(): Promise<ApiTradingMethod[]> {
  return apiFetch<ApiTradingMethod[]>('/api/stocks/methods')
}

/** Columns the ranking endpoint can sort by (must match the backend whitelist). */
export type RankingSortKey =
  | 'ticker'
  | 'name'
  | 'lastPrice'
  | 'priceChangePct'
  | 'currentRating'
  | 'ratingChange'
  | 'lastSignal'
  | 'daysSinceSignal'
  | 'volume'
  | 'sector'
  | 'aiConfidence'
  | 'distFrom52wHighPct'
  | 'distFrom52wLowPct'
  | 'weeklyRating'
  | 'combinedScore'

/** All server-side query options for the ranking feed. */
export interface RankingQuery {
  page?: number
  pageSize?: number
  /**
   * Sort levels, outermost first: `[{sector, asc}, {currentRating, desc}]` is
   * "sector A→Z, best rating first within each". One level is an ordinary
   * single-column sort. Serialised as `sortBy`/`sortDir` comma-separated lists.
   */
  sort?: SortLevel<RankingSortKey>[]
  /** Free-text search over ticker + name. */
  q?: string
  /** Minimum VSA rating (0 = no filter). */
  minRating?: number
  /** Maximum VSA rating (100 = no filter). */
  maxRating?: number
  /** Signal verdict filter, or 'all'/undefined for no filter. */
  signal?: SignalVerdict | 'all'
  /** Exact sector name, or 'all'/undefined for no filter. */
  sector?: string
  /** Only stocks whose last signal fired at most this many sessions ago. */
  maxDaysSinceSignal?: number
  /**
   * Price range. Read in each stock's own currency when one market is
   * requested, and in złoty when markets are pooled (`market=all`), where
   * "at least 100" would otherwise mean złoty, dollars or *pence* by row.
   */
  minPrice?: number
  maxPrice?: number
  /** Minimum 20-session median volume, shares. */
  minVolume?: number
  /** Only stocks trading within this many % of their 52-week high. */
  maxDistFrom52wHighPct?: number
  /** Only stocks trading within this many % above their 52-week low. */
  maxDistFrom52wLowPct?: number
  /** Only stocks whose latest session set a new 52-week high / low. */
  new52wHigh?: boolean
  new52wLow?: boolean
  /** Only stocks whose weekly VSA verdict confirms their daily one. */
  weeklyConfirms?: boolean
  /** Restrict results to these tickers (used by the "favorites only" view). */
  tickers?: string[]
  /**
   * Trading-method ids that fold into the combined cross-method score (and the
   * `combinedScore` sort). Unknown ids are ignored server-side; an empty/absent
   * value means "all methods".
   */
  methods?: string[]
  /** URL-encoded VSA settings JSON from the Scanner page. */
  settings?: string
  /** Market id, or 'all' for every served market (default: the GPW). */
  market?: string
}

/** One page of the ranking feed plus the total count of matching rows. */
export interface RankingPage {
  items: ApiRankingItem[]
  total: number
}

export async function fetchRanking(query: RankingQuery = {}): Promise<RankingPage> {
  const {
    page = 1,
    pageSize = 50,
    sort,
    q,
    minRating,
    maxRating,
    signal,
    sector,
    maxDaysSinceSignal,
    minPrice,
    maxPrice,
    minVolume,
    maxDistFrom52wHighPct,
    maxDistFrom52wLowPct,
    new52wHigh,
    new52wLow,
    weeklyConfirms,
    tickers,
    methods,
    settings,
    market,
  } = query

  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  })
  const sortParams = sort && serializeSort(sort)
  if (sortParams) {
    params.set('sortBy', sortParams.sortBy)
    params.set('sortDir', sortParams.sortDir)
  }
  if (q && q.trim()) params.set('q', q.trim())
  if (minRating && minRating > 0) params.set('minRating', String(minRating))
  if (maxRating !== undefined && maxRating < 100) {
    params.set('maxRating', String(maxRating))
  }
  if (signal && signal !== 'all') params.set('signal', signal)
  if (sector && sector !== 'all') params.set('sector', sector)
  if (maxDaysSinceSignal !== undefined) {
    params.set('maxDaysSinceSignal', String(maxDaysSinceSignal))
  }
  if (minPrice !== undefined && minPrice > 0) params.set('minPrice', String(minPrice))
  if (maxPrice !== undefined) params.set('maxPrice', String(maxPrice))
  if (minVolume !== undefined && minVolume > 0) {
    params.set('minVolume', String(minVolume))
  }
  if (maxDistFrom52wHighPct !== undefined) {
    params.set('maxDistFrom52wHighPct', String(maxDistFrom52wHighPct))
  }
  if (maxDistFrom52wLowPct !== undefined) {
    params.set('maxDistFrom52wLowPct', String(maxDistFrom52wLowPct))
  }
  if (new52wHigh) params.set('new52wHigh', 'true')
  if (new52wLow) params.set('new52wLow', 'true')
  if (weeklyConfirms) params.set('weeklyConfirms', 'true')
  if (tickers) params.set('tickers', tickers.join(','))
  if (methods && methods.length) params.set('methods', methods.join(','))
  if (settings) params.set('settings', settings)
  if (market) params.set('market', market)

  const { data, headers } = await apiFetchWithHeaders<ApiRankingItem[]>(
    `/api/stocks/ranking?${params}`,
  )
  const total = Number(headers.get('X-Total-Count') ?? data.length)
  return { items: data, total: Number.isFinite(total) ? total : data.length }
}

// ── GET /api/stocks/heatmap ───────────────────────────────────────────────────

export interface ApiHeatmapItem {
  ticker: string
  name: string
  sector: string | null
  market: string
  /** The currency `lastPrice` is in. */
  currency: string
  /** Market capitalisation (tile size) in the major unit of `currency`; null when not known. */
  marketCap: number | null
  lastPrice: number
  /** VSA rating 0–100 (tile color in the default view). */
  currentRating: number
  lastSignal: string
  /** % changes per horizon; null when stored history is too short. */
  change1D: number | null
  change1M: number | null
  change1Y: number | null
  /** Change vs the oldest stored bar (full stored history). */
  changeMax: number | null
  /**
   * Today's session so far while the exchange trades; `lastPrice` and every
   * change are then measured from its price (the rating stays the finished
   * session's). Absent on older backends.
   */
  live?: ApiLivePrice | null
}

export interface ApiHeatmapResponse {
  /** Trading day of the newest bar across all tiles. */
  asOf: string | null
  /** Tiles sorted by market cap, largest first. */
  items: ApiHeatmapItem[]
}

/** One market at a time — tiles are sized by market cap. */
export async function fetchHeatmap(
  settings?: string,
  market?: string,
): Promise<ApiHeatmapResponse> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  if (market) params.set('market', market)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiHeatmapResponse>(`/api/stocks/heatmap${qs}`)
}

// ── GET /api/stocks/market-overview ───────────────────────────────────────────

/** Counts over the ranked stocks — how the market leans, not a score. */
export interface ApiMarketBreadth {
  /** Stocks tallied (those the ranking shows). */
  total: number
  strongBuy: number
  buy: number
  hold: number
  sell: number
  strongSell: number
  /** Strong Buy + Buy, and Sell + Strong Sell, as a share of `total` (percent). */
  bullishPct: number
  bearishPct: number
  averageRating: number | null
  /** Stocks that rose / fell / were flat in the latest session. */
  advancers: number
  decliners: number
  unchanged: number
  /** Stocks whose rating rose / fell since the previous session. */
  ratingUp: number
  ratingDown: number
  new52wHighs: number
  new52wLows: number
}

export interface ApiRatingMover {
  ticker: string
  name: string
  market: string
  currency: string
  lastSession: string | null
  lastPrice: number
  priceChangePct: number
  /** Rating before the newest session, after it, and the difference. */
  previousRating: number
  currentRating: number
  ratingChange: number
  lastSignal: SignalVerdict
}

export interface ApiMarketOverview {
  asOf: string | null
  market: string
  breadth: ApiMarketBreadth
  /** Rating rose the most / fell the most; only stocks that actually moved. */
  moversUp: ApiRatingMover[]
  moversDown: ApiRatingMover[]
}

/** Breadth + rating movers of one market, or `all` of them together. */
export async function fetchMarketOverview(
  settings?: string,
  market?: string,
): Promise<ApiMarketOverview> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  if (market) params.set('market', market)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiMarketOverview>(`/api/stocks/market-overview${qs}`)
}

// ── GET /api/stocks/volume-surge ──────────────────────────────────────────────

export interface ApiVolumeSurgeItem {
  ticker: string
  name: string
  sector: string | null
  market: string
  /** The currency `lastPrice` is in. */
  currency: string
  lastPrice: number
  /** Average daily volume over the recent window (shares). */
  recentAvgVolume: number
  /**
   * Typical daily volume over the baseline window before it — the median
   * session since 2026-09-26, so one exceptional day cannot distort it
   * (shares). The name predates the change.
   */
  baselineAvgVolume: number
  /** Recent avg ÷ baseline — the multi-day relative volume (RVOL). */
  volumeRatio: number
  /** Latest single session's volume ÷ baseline (classic RVOL). */
  lastDayRatio: number
  /** Recent sessions whose volume individually beat the baseline. */
  daysAboveBaseline: number
  /** Price change across the recent window, % (the "result" of the effort). */
  priceChangePct: number
  /** VSA rating 0–100 (same window/settings as the ranking). */
  currentRating: number
  lastSignal: string
  /** Calendar days since the latest VSA signal; 999 = none. */
  daysSinceSignal: number
  /** A VSA signal falls inside the surge window (so the verdict speaks to it). */
  signalInWindow: boolean
  /** First session of the surge window (ISO date). */
  surgeStart: string
  /** The session in the window that traded the most shares (ISO date). */
  peakDate: string
  /** Its volume ÷ the baseline. */
  peakVolumeRatio: number
  /** Its close vs the close before it, % — an up bar or a down bar. */
  peakChangePct: number
  /** Its spread ÷ the baseline's average spread; null without a reference. */
  peakSpreadRatio: number | null
  /** Where it closed in its range: 0 = the low, 1 = the high; null = no range. */
  peakClosePosition: number | null
  /** The window traded above the baseline's highest high / below its lowest low. */
  breaksHigh: boolean
  breaksLow: boolean
  /** A company report dated in the window or the session before it (ISO). */
  reportDate: string | null
}

export interface ApiVolumeSurgeResponse {
  /** Trading day of the newest bar across the surging stocks. */
  asOf: string | null
  /** Echo of the screen parameters the results were computed with. */
  recentDays: number
  baselineDays: number
  minRatio: number
  /** Stocks that passed the pre-filters and had enough history to score. */
  scannedCount: number
  /** Surging stocks matching the screen, before pagination (pager total). */
  totalCount: number
  /** One page of surging stocks (server-side sorted). */
  items: ApiVolumeSurgeItem[]
}

/** Columns the volume-surge endpoint can sort by (backend whitelist). */
export type VolumeSurgeSortKey =
  | 'ticker'
  | 'name'
  | 'sector'
  | 'lastPrice'
  | 'recentAvgVolume'
  | 'baselineAvgVolume'
  | 'volumeRatio'
  | 'lastDayRatio'
  | 'daysAboveBaseline'
  | 'peakVolumeRatio'
  | 'priceChangePct'
  | 'currentRating'
  | 'lastSignal'

export interface VolumeSurgeQuery {
  /** Sessions in the "now" window (1–10, default 3). */
  recentDays?: number
  /** Sessions in the reference window before it (10–60, default 20). */
  baselineDays?: number
  /** Minimum RVOL ratio to include a stock (1–10, default 1.5). */
  minRatio?: number
  page?: number
  pageSize?: number
  /** Sort levels, outermost first (default: volumeRatio descending). */
  sort?: SortLevel<VolumeSurgeSortKey>[]
  /** URL-encoded VSA settings JSON from the Scanner page. */
  settings?: string
  /** Market id, or 'all' for every served market (default: the GPW). */
  market?: string
}

export async function fetchVolumeSurge(
  query: VolumeSurgeQuery = {},
): Promise<ApiVolumeSurgeResponse> {
  const params = new URLSearchParams()
  if (query.recentDays) params.set('recentDays', String(query.recentDays))
  if (query.baselineDays) params.set('baselineDays', String(query.baselineDays))
  if (query.minRatio) params.set('minRatio', String(query.minRatio))
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('pageSize', String(query.pageSize))
  const surgeSort = query.sort && serializeSort(query.sort)
  if (surgeSort) {
    params.set('sortBy', surgeSort.sortBy)
    params.set('sortDir', surgeSort.sortDir)
  }
  if (query.settings) params.set('settings', query.settings)
  if (query.market) params.set('market', query.market)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiVolumeSurgeResponse>(`/api/stocks/volume-surge${qs}`)
}

// ── GET /api/stocks/capex ─────────────────────────────────────────────────────

/**
 * How much a company invests in its own business (capital expenditure).
 *
 * All money figures are in `currency` and positive = money spent. Any of them
 * can be null: Yahoo has no usable capex for some companies, and "not
 * reported" is deliberately not shown as zero. `basis` says which period the
 * headline `capex` and the ratios describe, so a yearly and a 12-month figure
 * are never silently compared.
 */
export interface ApiCapexSummary {
  currency: string | null
  basis: 'ttm' | 'annual' | null
  /** Headline capex: last four quarters, or the latest full year. */
  capex: number | null
  capexTtm: number | null
  capexAnnual: number | null
  annualPeriodEnd: string | null
  capexPrevAnnual: number | null
  /** Change in yearly capex vs the year before, %. */
  capexGrowthYoyPct: number | null
  /** Capex as a share of revenue, % — capital intensity. */
  capexToRevenuePct: number | null
  /** Capex as a share of operating cash flow, % — above 100 = not self-funded. */
  capexToOcfPct: number | null
  operatingCashFlow: number | null
}

export interface ApiCapexItem extends ApiCapexSummary {
  ticker: string
  name: string
  sector: string | null
  market: string
}

export interface ApiCapexResponse {
  /** Newest reporting period end across all companies. */
  asOf: string | null
  /** Companies matching the filters before pagination (pager total). */
  totalCount: number
  /** Of the whole universe, how many have any capex figure at all. */
  withDataCount: number
  /** Companies considered before filtering. */
  scannedCount: number
  items: ApiCapexItem[]
}

/** Columns the capex endpoint can sort by (backend whitelist). */
export type CapexSortKey =
  | 'ticker'
  | 'name'
  | 'sector'
  | 'capex'
  | 'capexTtm'
  | 'capexAnnual'
  | 'capexGrowthYoyPct'
  | 'capexToRevenuePct'
  | 'capexToOcfPct'
  | 'operatingCashFlow'

export interface CapexQuery {
  /** Free-text search over ticker + name. */
  q?: string
  /** Exact sector name, or 'all'/undefined for no filter. */
  sector?: string
  /**
   * Reporting currency; absent = the market's own (PLN for the GPW, USD for
   * the US…) — amounts in different currencies are not comparable. 'all'
   * lifts the filter.
   */
  currency?: string
  /** One market per request (default: the GPW). */
  market?: string
  /** False keeps companies with no reported capex (blank rows). */
  withData?: boolean
  page?: number
  pageSize?: number
  /** Sort levels, outermost first (default: capex descending). */
  sort?: SortLevel<CapexSortKey>[]
}

export async function fetchCapex(query: CapexQuery = {}): Promise<ApiCapexResponse> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.sector && query.sector !== 'all') params.set('sector', query.sector)
  if (query.currency) params.set('currency', query.currency)
  if (query.withData === false) params.set('withData', 'false')
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('pageSize', String(query.pageSize))
  const capexSort = query.sort && serializeSort(query.sort)
  if (capexSort) {
    params.set('sortBy', capexSort.sortBy)
    params.set('sortDir', capexSort.sortDir)
  }
  if (query.market) params.set('market', query.market)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiCapexResponse>(`/api/stocks/capex${qs}`)
}

// ── POST /api/stocks/refresh + GET /api/stocks/refresh/status ────────────────

export interface ApiRefreshStatus {
  /** "running" while the backend downloads data and recalculates ratings. */
  state: 'idle' | 'running'
  lastStartedAt: string | null
  /** When the last refresh finished successfully (ISO datetime). */
  lastRefreshAt: string | null
  lastError: string | null
  /** Stocks that passed the pre-filters in the last completed run. */
  stocksRanked: number | null
  /** False = no PostgreSQL, so rating history is not being stored. */
  dbEnabled: boolean
  /**
   * When today's live prices last changed (ISO), across markets — a page left
   * open polls this to learn there is something new. Absent on older backends.
   */
  livePricesAt?: string | null
  /** Per market id, when its live prices were last downloaded today (ISO). */
  liveMarkets?: Record<string, string>
}

/** Start a full data refresh (Yahoo download → ratings → saved snapshots). */
export async function triggerRefresh(): Promise<ApiRefreshStatus> {
  return apiFetch<ApiRefreshStatus>('/api/stocks/refresh', { method: 'POST' })
}

export async function fetchRefreshStatus(): Promise<ApiRefreshStatus> {
  return apiFetch<ApiRefreshStatus>('/api/stocks/refresh/status')
}

// ── GET /api/stocks/{ticker}/rating-history ──────────────────────────────────

export interface ApiRatingPoint {
  date: string
  /** VSA rating 0–100 on that day (default engine settings). */
  rating: number
  verdict: string
  close: number | null
}

export interface ApiRatingHistory {
  ticker: string
  name: string | null
  /** The currency the points' closing prices are in. */
  currency?: string
  points: ApiRatingPoint[]
  /** "db" = stored snapshots; "computed" = derived on the fly (no history yet). */
  source: 'db' | 'computed'
}

export async function fetchRatingHistory(
  ticker: string,
  fromDate?: string,
  toDate?: string,
): Promise<ApiRatingHistory> {
  const params = new URLSearchParams()
  if (fromDate) params.set('fromDate', fromDate)
  if (toDate) params.set('toDate', toDate)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiRatingHistory>(
    `/api/stocks/${encodeURIComponent(ticker)}/rating-history${qs}`,
  )
}

// ── GET /api/stocks/scanner/stats ────────────────────────────────────────────

export interface ApiSignalEffectiveness {
  signal: string
  count: number
  successPct: number
  /**
   * Reward/risk ratio (baseline-excess frame). `null` means the ratio is
   * undefined: either the back-test found wins but no losses (the best
   * possible outcome — render as "—", sort as +Infinity) or there were no
   * judged occurrences at all (count is 0 in that case).
   */
  rewardRisk: number | null
  activeCount: number
}

export async function fetchScannerStats(
  settings?: string,
  market?: string,
): Promise<ApiSignalEffectiveness[]> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  if (market) params.set('market', market)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiSignalEffectiveness[]>(`/api/stocks/scanner/stats${qs}`)
}

// ── GET /api/stocks/{ticker}/signals ─────────────────────────────────────────

/** One bar a trading method marked on the chart — a firing, or a near miss. */
export interface ApiMethodSignal {
  date: string
  /** Short on-chart tag, e.g. "Trend Template". */
  label: string
  /**
   * "Bullish"/"Bearish" are firings — the setup was taken. "Watch" is a bar
   * the method assessed and did NOT take, its `label` carrying the reason
   * (VSA V3's near misses); it is never counted as a trade.
   */
  type: 'Bullish' | 'Bearish' | 'Watch'
}

/** All chart-overlay markers for one trading method (excludes VSA). */
export interface ApiMethodSignalGroup {
  methodId: string
  name: string
  direction: string
  signals: ApiMethodSignal[]
}

export interface ApiStockSignals {
  ticker: string
  name: string | null
  sector: string | null
  /** Where the stock trades; absent from older backends (then: the GPW). */
  market?: string
  /** The currency the price and every candle are in. */
  currency?: string
  /** The listing venue ("GPW", "NASDAQ", "Xetra"…). */
  exchange?: string | null
  lastPrice: number
  priceChangePct: number
  currentRating: number
  ratingChange: number
  history: Candle[]  // backend returns { time, open, high, low, close, volume }
  vsaSignals: VsaSignal[]
  /**
   * Per-method chart overlays for every method OTHER than VSA (whose markers
   * are `vsaSignals`). Empty on older backends; each group may itself be empty
   * when that method never fired in the window.
   */
  methodSignals: ApiMethodSignalGroup[]
  /** Bar size of `history` / `vsaSignals` — see `ChartInterval`. */
  interval: ChartInterval
  /** True when the bars are intraday moments rather than whole sessions. */
  intraday: boolean
  /**
   * Oldest bar the source could actually serve (YYYY-MM-DD). Intraday history
   * is capped upstream (~60 days at 30m), so this can start later than the
   * requested `fromDate` — the chart says so rather than pretending.
   */
  historyStart: string | null
  /**
   * Multi-timeframe (weekly) confirmation of the DAILY read — the same three
   * fields the ranking rows carry, from the same engine and window, so the
   * stock page and the dashboard's "1W" chip always agree. Like the rating,
   * these do NOT follow the chart's `interval`. All three are null when the
   * stock has under ~30 weeks of stored history (and on older backends).
   */
  weeklyRating: number | null
  weeklySignal: SignalVerdict | null
  weeklyAgreement: WeeklyAgreement | null
  /**
   * Today's session so far while the exchange trades — only on a chart that
   * reaches today. `lastPrice`/`priceChangePct` are then its figures; the
   * rating, `history` and every marker stay on finished sessions, so the chart
   * draws it as a separate, still-forming candle. Absent on older backends.
   */
  live?: ApiLivePrice | null
}

/**
 * Chart bar sizes. `1d` is the app's native timeframe (everything else on the
 * page — rating, ranking, methods — is computed on daily bars); `1w` is
 * aggregated from it, and the intraday ones are fetched just for the chart.
 */
export type ChartInterval = '30m' | '1h' | '4h' | '1d' | '1w'

export async function fetchSignals(
  ticker: string,
  fromDate?: string,
  toDate?: string,
  settings?: string,
  interval?: ChartInterval,
): Promise<ApiStockSignals> {
  const params = new URLSearchParams()
  if (fromDate) params.set('fromDate', fromDate)
  if (toDate) params.set('toDate', toDate)
  if (settings) params.set('settings', settings)
  if (interval) params.set('interval', interval)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiStockSignals>(`/api/stocks/${encodeURIComponent(ticker)}/signals${qs}`)
}

// ── GET /api/stocks/{ticker}/ai-analysis ─────────────────────────────────────

export interface ApiAiSignalAssessment {
  date: string
  signalName: string
  /** Whether the chart context supports the rule-detected signal. */
  agreement: 'confirm' | 'reject' | 'uncertain'
  comment: string
}

export interface ApiAiAnalysis {
  ticker: string
  /** Trading day of the last bar the analysis is based on. */
  asOf: string
  verdict: SignalVerdict
  /** Engine conviction, 0–100. */
  confidence: number
  /** Plain-language narrative of the price/volume action. */
  summary: string
  /** Per-signal second opinions, newest first. */
  signalAssessments: ApiAiSignalAssessment[]
  keyObservations: string[]
  /** Built-in engine identifier, e.g. "stockpilot-insight-1". */
  engine: string
}

export async function fetchAiAnalysis(
  ticker: string,
  settings?: string,
): Promise<ApiAiAnalysis> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiAiAnalysis>(
    `/api/stocks/${encodeURIComponent(ticker)}/ai-analysis${qs}`,
  )
}

// ── GET /api/stocks/{ticker}/trust-score ─────────────────────────────────────

export interface ApiTrustScoreEvent {
  date: string
  signalName: string
  /** The verdict the signal mapped to when it fired. */
  verdict: 'Strong Buy' | 'Strong Sell'
  /** Actual % move over the sessions after the signal. */
  forwardReturnPct: number
  /** The stock's typical (median) move over the same horizon, %. */
  baselineReturnPct: number
  /** Edge vs. baseline in the signal's direction, percentage points. */
  excessReturnPct: number
  /** True when the signal beat the baseline in its direction. */
  goodEntry: boolean
}

export interface ApiTrustScore {
  ticker: string
  /** Trading day of the last bar the back-test is based on. */
  asOf: string
  /** 0–100 trust score; null when no strong signal is old enough to judge. */
  score: number | null
  grade: 'high' | 'medium' | 'low' | 'insufficient'
  /** Sessions a paper entry is held before it is judged. */
  horizonSessions: number
  /** Strong signals old enough to judge / of those, good entries. */
  evaluatedCount: number
  goodCount: number
  /** Strong signals too recent to judge yet. */
  freshCount: number
  buyEvaluated: number
  buyGood: number
  sellEvaluated: number
  sellGood: number
  baselineReturnPct: number | null
  avgExcessReturnPct: number | null
  /** Plain-language explanation of the track record. */
  summary: string
  /** Back-tested strong signals, newest first. */
  events: ApiTrustScoreEvent[]
  /** Built-in engine identifier, e.g. "stockpilot-trust-1". */
  engine: string
}

export async function fetchTrustScore(
  ticker: string,
  settings?: string,
): Promise<ApiTrustScore> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiTrustScore>(
    `/api/stocks/${encodeURIComponent(ticker)}/trust-score${qs}`,
  )
}

// ── GET /api/stocks/{ticker}/opinion-summary ─────────────────────────────────

/** The consolidated direction across the app's per-stock opinions. */
export type OpinionStance = 'bullish' | 'bearish' | 'neutral' | 'mixed'

/** One analytical engine's contribution to the consolidated opinion. */
export interface ApiOpinionSource {
  /** Stable key, e.g. "vsa", "aiInsight", "trustScore", "minervini". */
  key: string
  label: string
  /** "direction" sources vote on the consensus; "reliability" ones don't. */
  kind: 'direction' | 'reliability'
  /**
   * For a direction source: its bullish/bearish/neutral lean. For the
   * reliability source: bullish = reliable, bearish = unreliable, neutral =
   * mixed. "unavailable" = could not be evaluated.
   */
  stance: 'bullish' | 'bearish' | 'neutral' | 'unavailable'
  /** Compact value, e.g. "Buy · 72/100", "6/7 rules". */
  headline: string
  /** One plain-language sentence explaining this source's read. */
  detail: string
  /** The source's entry setup fired in the last few sessions (methods only). */
  firedRecently: boolean
}

export interface ApiAnalyticsSummary {
  ticker: string
  name: string | null
  /** Trading day of the last bar the summary is based on. */
  asOf: string
  stance: OpinionStance
  /** 0–100 — how strongly the directional sources agree with each other. */
  agreement: number
  /** One-line takeaway. */
  headline: string
  /** Plain-language paragraph reconciling the sources. */
  summary: string
  /** Per-source breakdown (direction sources first, reliability last). */
  sources: ApiOpinionSource[]
  /** Built-in engine identifier, e.g. "stockpilot-summary-1". */
  engine: string
}

export async function fetchOpinionSummary(
  ticker: string,
  settings?: string,
): Promise<ApiAnalyticsSummary> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiAnalyticsSummary>(
    `/api/stocks/${encodeURIComponent(ticker)}/opinion-summary${qs}`,
  )
}

// ── GET /api/stocks/{ticker}/fundamentals ────────────────────────────────────

export interface ApiFinancialMetrics {
  updatedAt: string | null
  marketCap: number | null
  peRatio: number | null
  forwardPe: number | null
  eps: number | null
  dividendYield: number | null
  totalRevenue: number | null
  netIncome: number | null
  sharesOutstanding: number | null
  /** The currency revenue, net income and EPS are reported in. */
  financialCurrency?: string | null
  /** Profitability ratios as fractions (0.184 = 18.4%). */
  returnOnEquity: number | null
  returnOnAssets: number | null
}

/**
 * Trailing price returns, percent. Computed from the stored EOD bars, so a
 * horizon is null when the stored history doesn't reach back that far.
 * These ignore dividends — price return, not total return.
 */
export interface ApiPriceReturns {
  ytdPct: number | null
  y1Pct: number | null
  y3Pct: number | null
  y5Pct: number | null
  /** Change over the whole stored history, and the date it starts from. */
  maxPct: number | null
  maxFromDate: string | null
}

export interface ApiQuarterlyReport {
  periodEnd: string
  totalRevenue: number | null
  netIncome: number | null
  operatingIncome: number | null
  eps: number | null
}

export interface ApiFundamentals {
  ticker: string
  name: string | null
  sector: string | null
  description: string | null
  industry: string | null
  employees: number | null
  website: string | null
  country: string | null
  market?: string
  /** The currency the shares trade in (the market cap is in its major unit). */
  currency?: string
  exchange?: string | null
  metrics: ApiFinancialMetrics | null
  quarterlyReports: ApiQuarterlyReport[]
  /** Trailing price returns from the stored bars; null if unavailable. */
  priceReturns: ApiPriceReturns | null
  /** Last four reported quarters summed; null when fewer than four exist. */
  ttmRevenue: number | null
  ttmNetIncome: number | null
  /** Investment spending; null when Yahoo has no cash-flow statement. */
  capex: ApiCapexSummary | null
}

export async function fetchFundamentals(ticker: string): Promise<ApiFundamentals> {
  return apiFetch<ApiFundamentals>(
    `/api/stocks/${encodeURIComponent(ticker)}/fundamentals`,
  )
}

// ── GET /api/stocks/{ticker}/volume ──────────────────────────────────────────

/**
 * One stock's multi-day relative-volume (RVOL) reading — the single-ticker
 * form of the /volume-surge screen. All figures are null (and `available` is
 * false) when the stored history is shorter than the two windows combined.
 */
export interface ApiTickerVolume {
  ticker: string
  /** Trading day of the last bar the reading is based on. */
  asOf: string | null
  /** Windows used: last `recentDays` sessions vs the `baselineDays` before. */
  recentDays: number
  baselineDays: number
  available: boolean
  recentAvgVolume: number | null
  /** Typical (median) daily volume of the baseline window. */
  baselineAvgVolume: number | null
  /** recent avg ÷ baseline — multi-day RVOL (1.0 = a typical session). */
  volumeRatio: number | null
  /** Latest single session's volume ÷ baseline (classic RVOL). */
  lastDayRatio: number | null
  /** Recent sessions whose volume individually beat the baseline. */
  daysAboveBaseline: number | null
  /** Close-to-close price change across the recent window, percent. */
  priceChangePct: number | null
  /** Latest session's raw volume (shares). */
  lastVolume: number | null
}

export async function fetchTickerVolume(ticker: string): Promise<ApiTickerVolume> {
  return apiFetch<ApiTickerVolume>(
    `/api/stocks/${encodeURIComponent(ticker)}/volume`,
  )
}

// ── GET /api/stocks/{ticker}/trade-simulation ────────────────────────────────

/** Which setups the simulated account takes: long only (default) or both. */
export type SimulationSides = 'long' | 'both'

/** One trade from the VSA V4 program's own simulator. */
export interface ApiSimulatedTrade {
  /** "open" = still held at the last bar, valued at its close. */
  status: 'closed' | 'open'
  direction: 'long' | 'short'
  /** The confirmation bar; the entry is the next session's open. */
  signalDate: string
  entryDate: string
  exitDate: string | null
  /** "Selling Climax → No Supply": the sequence's primary → its test. */
  setup: string
  entryPrice: number
  stopLoss: number
  takeProfit: number
  exitPrice: number | null
  /** stop | take_profit | stop_gap_open | take_profit_gap_open |
   *  stop_same_bar_both_hit | end_of_data_close | open_at_end */
  exitReason: string
  quantity: number
  /** Net of both commissions and slippage, in the account's money. */
  netPnl: number
  /** Net result in multiples of the planned risk (entry-to-stop distance). */
  netR: number | null
  /** Price move from entry to exit (or last close) in the trade's favour, %. */
  returnPct: number | null
}

export interface ApiEquityPoint {
  date: string
  equity: number
  drawdownPct: number
}

/**
 * The owner's VSA program (method "VSA V4") replayed over this stock's stored
 * history with its own simulator: next-open entries, a structural stop, a 3R
 * target, one position at a time, a fixed share of the account risked per
 * trade. Educational, not a forecast.
 */
export interface ApiTradeSimulation {
  ticker: string
  methodId: string
  /** The stock's own quote currency — every price is in it. */
  currency: string | null
  fromDate: string | null
  asOf: string | null
  barCount: number
  sides: SimulationSides
  initialCapital: number
  riskPct: number
  rewardRisk: number
  /** Per side, percent (0.2 = 0.20%). */
  commissionPct: number
  slippagePct: number
  finalEquity: number
  totalReturnPct: number
  maxDrawdownPct: number
  closedTrades: number
  openTrades: number
  wins: number
  losses: number
  /** Share of closed trades that made money after costs; null with none. */
  winRatePct: number | null
  /** Gross wins ÷ gross losses; null when nothing lost. */
  profitFactor: number | null
  /** Mean net R per closed trade — the expectancy in units of risk. */
  avgR: number | null
  skippedEntries: number
  longSetups: number
  shortSetups: number
  /** Buy on the first simulated close, hold to the last — a reference only. */
  buyHoldReturnPct: number | null
  trades: ApiSimulatedTrade[]
  equity: ApiEquityPoint[]
  engine: string
}

export async function fetchTradeSimulation(
  ticker: string,
  sides: SimulationSides = 'long',
): Promise<ApiTradeSimulation> {
  const qs = sides === 'long' ? '' : `?sides=${sides}`
  return apiFetch<ApiTradeSimulation>(
    `/api/stocks/${encodeURIComponent(ticker)}/trade-simulation${qs}`,
  )
}

// ── GET /api/stocks/{ticker}/insider-transactions ────────────────────────────

export type {
  InsiderChartMarker as ApiInsiderChartMarker,
  InsiderSummary as ApiInsiderSummary,
  InsiderTransactionItem as ApiInsiderTransactionItem,
  InsiderTransactionsResponse as ApiInsiderTransactionsResponse,
} from '../types'
import type { InsiderTransactionsResponse } from '../types'

export async function fetchInsiderTransactions(
  ticker: string,
  options?: { includeAll?: boolean; fromDate?: string },
): Promise<InsiderTransactionsResponse> {
  const params = new URLSearchParams()
  if (options?.includeAll) params.set('includeAll', 'true')
  if (options?.fromDate) params.set('fromDate', options.fromDate)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<InsiderTransactionsResponse>(
    `/api/stocks/${encodeURIComponent(ticker)}/insider-transactions${qs}`,
  )
}

