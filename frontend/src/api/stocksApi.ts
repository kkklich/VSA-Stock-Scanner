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
  /** Signal verdict filter, or 'all'/undefined for no filter. */
  signal?: SignalVerdict | 'all'
  /** Restrict results to these tickers (used by the "favorites only" view). */
  tickers?: string[]
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
    signal,
    tickers,
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
  if (signal && signal !== 'all') params.set('signal', signal)
  if (tickers) params.set('tickers', tickers.join(','))
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
  rewardRisk: number
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
}

export async function fetchSignals(
  ticker: string,
  fromDate?: string,
  toDate?: string,
  settings?: string,
): Promise<ApiStockSignals> {
  const params = new URLSearchParams()
  if (fromDate) params.set('fromDate', fromDate)
  if (toDate) params.set('toDate', toDate)
  if (settings) params.set('settings', settings)
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
}

export async function fetchFundamentals(ticker: string): Promise<ApiFundamentals> {
  return apiFetch<ApiFundamentals>(
    `/api/stocks/${encodeURIComponent(ticker)}/fundamentals`,
  )
}
