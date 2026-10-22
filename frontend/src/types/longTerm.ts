/** QVM inputs are fractions (0.12 = 12%); scores and coverage are 0–100. */
export interface LongTermItem {
  ticker: string
  name: string
  sector: string | null
  market: string
  currency: string
  asOf: string | null
  score: number | null
  qualityScore: number | null
  valueScore: number | null
  momentumScore: number | null
  coverage: number
  eligible: boolean
  missing: string[]
  inputs: Record<string, number | null>
  fundamentalsObservedAt: string | null
  comparisonGroup: string
  peerCount: number
}

export interface LongTermRanking {
  market: string
  asOf: string | null
  modelVersion: string
  dbEnabled: boolean
  items: LongTermItem[]
  totalCount: number
  scoredCount: number
}

export interface LongTermSnapshot extends LongTermItem {
  recordedAt: string
  modelVersion: string
}

export interface FinancialObservation {
  observedAt: string
  kind: 'fundamentals' | 'quarterly' | 'cashflow'
  source: string
  payload: Record<string, unknown>
}

export interface HistoryResponse<T> {
  ticker: string
  dbEnabled: boolean
  items: T[]
}
