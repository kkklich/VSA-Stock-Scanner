// Typed API calls for the /api/stocks/* endpoints.
// Shapes mirror the Pydantic models in backend-python/app/models/stocks.py.

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

export async function fetchRanking(page = 1, pageSize = 50): Promise<ApiRankingItem[]> {
  return apiFetch<ApiRankingItem[]>(
    `/api/stocks/ranking?page=${page}&pageSize=${pageSize}`,
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

export async function fetchScannerStats(): Promise<ApiSignalEffectiveness[]> {
  return apiFetch<ApiSignalEffectiveness[]>('/api/stocks/scanner/stats')
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
): Promise<ApiStockSignals> {
  const params = new URLSearchParams()
  if (fromDate) params.set('fromDate', fromDate)
  if (toDate) params.set('toDate', toDate)
  const qs = params.size > 0 ? `?${params}` : ''
  return apiFetch<ApiStockSignals>(`/api/stocks/${encodeURIComponent(ticker)}/signals${qs}`)
}
