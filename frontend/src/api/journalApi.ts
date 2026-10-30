import { apiFetch } from './client'
import type { ChartInterval } from './stocksApi'
import type { Candle } from '../types'
import type { MethodOverlay } from '../components/StockChart'

export type JournalStatus = 'observing' | 'confirmed' | 'invalidated' | 'closed'
export interface JournalSnapshot {
  schemaVersion: 1
  name: string
  currency: string
  market: string
  interval: ChartInterval
  referencePrice: number
  rating: number | null
  combinedScore: number | null
  ratingSession: string | null
  methodScores: { methodId: string; score: number | null; detail: string | null }[]
  history: Candle[]
  overlays: MethodOverlay[]
}
export interface JournalSummary {
  id: string
  ticker: string
  note: string
  confirmation: string
  invalidation: string
  status: JournalStatus
  review: string
  version: number
  createdAt: string
  updatedAt: string
}
export interface JournalEntry extends JournalSummary { snapshot: JournalSnapshot }
export interface JournalPage { items: JournalSummary[]; total: number }
export interface NewJournalEntry {
  id: string; ticker: string; note: string; confirmation: string; invalidation: string
  snapshot: JournalSnapshot
}
export function journalRequest<T>(method: string, path = '', body?: unknown, signal?: AbortSignal) {
  return apiFetch<T>(`/api/journal${path}`, {
    method, signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
}
