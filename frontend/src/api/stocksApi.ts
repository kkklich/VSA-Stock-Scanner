// Typed API calls for the /api/stocks/* endpoints.
// Shapes mirror the Pydantic models in backend-python/app/models/stocks.py.
//
// All analysis endpoints accept an optional `settings` value (JSON string from
// lib/vsaSettings.ts) so the user's Scanner configuration drives the actual
// VSA calculation on the backend.

import { apiFetch } from './client'
import type { Candle, SignalVerdict, VsaSignal } from '../types'

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
}

export async function fetchRanking(
  page = 1,
  pageSize = 50,
  settings?: string,
): Promise<ApiRankingItem[]> {
  const params = new URLSearchParams({ page: String(page), pageSize: String(pageSize) })
  if (settings) params.set('settings', settings)
  return apiFetch<ApiRankingItem[]>(`/api/stocks/ranking?${params}`)
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
