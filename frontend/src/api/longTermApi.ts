import { apiFetch } from './client'
import type { FinancialObservation, HistoryResponse, LongTermRanking, LongTermSnapshot } from '../types/longTerm'

export function fetchLongTermRanking(market: string, signal: AbortSignal) {
  return apiFetch<LongTermRanking>(`/api/stocks/long-term?market=${encodeURIComponent(market)}`, { signal })
}

export function fetchLongTermHistory(ticker: string, signal: AbortSignal) {
  return apiFetch<HistoryResponse<LongTermSnapshot>>(
    `/api/stocks/${encodeURIComponent(ticker)}/long-term-history?limit=100`, { signal },
  )
}

export function fetchFinancialHistory(ticker: string, signal: AbortSignal) {
  return apiFetch<HistoryResponse<FinancialObservation>>(
    `/api/stocks/${encodeURIComponent(ticker)}/financial-history?limit=50`, { signal },
  )
}
