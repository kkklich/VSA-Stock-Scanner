import { apiFetch } from './client'

export interface Instrument { ticker: string; name: string; market: string; currency: string }
export interface Transaction {
  id: string; ticker: string; date: string; side: 'buy' | 'sell'
  quantity: string; price: string; fees: string; currency: string
  source?: 'xtb'; sourceId?: string; executedAt?: string
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

export interface XtbPreviewRow {
  sheet: string; row: number; symbol: string
  status: 'ready' | 'duplicate' | 'error'; code?: string; transaction?: Transaction
}
export interface XtbPreview {
  version: number; rows: XtbPreviewRow[]; ready: number; duplicates: number
  errors: number; ignored: number; warnings: string[]; ledgerError: string | null
}
export interface XtbImportResult { imported: number; duplicates: number; skipped: number; version: number }
export function previewXtb(portfolioId: string, file: File, signal: AbortSignal) {
  return uploadXtb<XtbPreview>(portfolioId, file, true, signal)
}
export function importXtb(portfolioId: string, file: File, version: number, allowPartial: boolean, signal: AbortSignal) {
  return uploadXtb<XtbImportResult>(portfolioId, file, false, signal, version, allowPartial)
}
function uploadXtb<T>(portfolioId: string, file: File, preview: boolean, signal: AbortSignal, version?: number, allowPartial = false) {
  const query = new URLSearchParams({ filename: file.name })
  if (version !== undefined) query.set('version', String(version))
  if (allowPartial) query.set('allow_partial', 'true')
  return apiFetch<T>(`/api/portfolios/${portfolioId}/imports/xtb${preview ? '/preview' : ''}?${query}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file, signal,
  })
}
