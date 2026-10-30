import { apiFetch } from './client'

export interface Instrument { ticker: string; name: string; market: string; currency: string }
export interface Transaction {
  id: string; ticker: string; date: string; side: 'buy' | 'sell'
  quantity: string; price: string; fees: string; currency: string
}
export interface PortfolioTotal {
  currency: string; cost: number; marketValue: number | null
  unrealizedPnl: number | null; unrealizedPnlPct: number | null
  realizedPnl: number; missingQuotes: number
}
export interface Position {
  ticker: string; currency: string; quantity: number; cost: number
  averagePrice: number | null; currentPrice: number | null
  marketValue: number | null; unrealizedPnl: number | null
  unrealizedPnlPct: number | null; realizedPnl: number
  quoteDate: string | null; quoteAsOf: string | null
  quoteSource: 'close' | 'intraday' | null; quoteAgeDays: number | null
}
export interface Portfolio {
  id: string; name: string; broker: string; version: number; createdAt: string
  costMethod: 'fifo' | 'moving_average'
  transactions: Transaction[]; positions: Position[]; totals: PortfolioTotal[]
}
export interface Portfolios { items: Portfolio[]; valuedAt: string }
export function portfolioRequest<T>(method: string, path = '', body?: unknown, signal?: AbortSignal) {
  return apiFetch<T>(`/api/portfolios${path}`, {
    method, signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
}
