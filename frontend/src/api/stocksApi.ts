// Typed API calls for the /api/stocks/* endpoints.
// Shapes mirror the Pydantic models in backend-python/app/models/stocks.py.
//
// All analysis endpoints accept an optional `settings` value (JSON string from
// lib/vsaSettings.ts) so the user's Scanner configuration drives the actual
// VSA calculation on the backend.

import { apiFetch, apiFetchWithHeaders } from './client'
import type { Candle, SignalVerdict, VsaSignal } from '../types'

// ── GET /api/stocks (tracked GPW companies) ───────────────────────────────────

export interface ApiCompany {
  ticker: string
  name: string
  sector: string | null
}

export async function fetchCompanies(): Promise<ApiCompany[]> {
  return apiFetch<ApiCompany[]>('/api/stocks')
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

export type SortDir = 'asc' | 'desc'

/** All server-side query options for the ranking feed. */
export interface RankingQuery {
  page?: number
  pageSize?: number
  sortBy?: RankingSortKey
  sortDir?: SortDir
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
  /** Price range in PLN (either bound optional). */
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
    sortBy,
    sortDir,
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
  } = query

  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  })
  if (sortBy) params.set('sortBy', sortBy)
  if (sortDir) params.set('sortDir', sortDir)
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
  /** Market capitalisation in PLN (tile size); null when not known. */
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
}

export interface ApiHeatmapResponse {
  /** Trading day of the newest bar across all tiles. */
  asOf: string | null
  /** Tiles sorted by market cap, largest first. */
  items: ApiHeatmapItem[]
}

export async function fetchHeatmap(settings?: string): Promise<ApiHeatmapResponse> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiHeatmapResponse>(`/api/stocks/heatmap${qs}`)
}

// ── GET /api/stocks/volume-surge ──────────────────────────────────────────────

export interface ApiVolumeSurgeItem {
  ticker: string
  name: string
  sector: string | null
  lastPrice: number
  /** Average daily volume over the recent window (shares). */
  recentAvgVolume: number
  /** Average daily volume over the baseline window before it (shares). */
  baselineAvgVolume: number
  /** Recent avg ÷ baseline avg — the multi-day relative volume (RVOL). */
  volumeRatio: number
  /** Latest single session's volume ÷ baseline avg (classic RVOL). */
  lastDayRatio: number
  /** Recent sessions whose volume individually beat the baseline average. */
  daysAboveBaseline: number
  /** Price change across the recent window, % (the "result" of the effort). */
  priceChangePct: number
  /** VSA rating 0–100 (same window/settings as the ranking). */
  currentRating: number
  lastSignal: string
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
  /** Sort column (default volumeRatio). */
  sortBy?: VolumeSurgeSortKey
  sortDir?: SortDir
  /** URL-encoded VSA settings JSON from the Scanner page. */
  settings?: string
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
  if (query.sortBy) params.set('sortBy', query.sortBy)
  if (query.sortDir) params.set('sortDir', query.sortDir)
  if (query.settings) params.set('settings', query.settings)
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
   * Reporting currency, default 'PLN' — amounts in different currencies are
   * not comparable. 'all' lifts the filter.
   */
  currency?: string
  /** False keeps companies with no reported capex (blank rows). */
  withData?: boolean
  page?: number
  pageSize?: number
  /** Sort column (default capex). */
  sortBy?: CapexSortKey
  sortDir?: SortDir
}

export async function fetchCapex(query: CapexQuery = {}): Promise<ApiCapexResponse> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.sector && query.sector !== 'all') params.set('sector', query.sector)
  if (query.currency) params.set('currency', query.currency)
  if (query.withData === false) params.set('withData', 'false')
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('pageSize', String(query.pageSize))
  if (query.sortBy) params.set('sortBy', query.sortBy)
  if (query.sortDir) params.set('sortDir', query.sortDir)
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
): Promise<ApiSignalEffectiveness[]> {
  const params = new URLSearchParams()
  if (settings) params.set('settings', settings)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiSignalEffectiveness[]>(`/api/stocks/scanner/stats${qs}`)
}

// ── GET /api/stocks/{ticker}/signals ─────────────────────────────────────────

/** One bar where a trading method's setup fired — a chart overlay marker. */
export interface ApiMethodSignal {
  date: string
  /** Short on-chart tag, e.g. "Trend Template". */
  label: string
  type: 'Bullish' | 'Bearish'
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
  baselineAvgVolume: number | null
  /** recent avg ÷ baseline avg — multi-day RVOL (1.0 = normal activity). */
  volumeRatio: number | null
  /** Latest single session's volume ÷ baseline avg (classic RVOL). */
  lastDayRatio: number | null
  /** Recent sessions whose volume individually beat the baseline average. */
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
