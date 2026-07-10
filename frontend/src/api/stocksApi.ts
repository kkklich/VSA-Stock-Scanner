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
