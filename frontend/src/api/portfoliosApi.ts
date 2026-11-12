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
  reconciliation?: XtbReconciliation | null
}
export interface PortfolioSummaryPoint {
  date: string; value: number | null; missingQuotes: number; missingRates: string[]; staleQuotes: number
}
export interface PortfolioSummaryChange { amount: number; percent: number | null; since: string }
export interface PortfolioSummary {
  currency: string; current: PortfolioSummaryPoint; history: PortfolioSummaryPoint[]
  dayChange: PortfolioSummaryChange | null; weekChange: PortfolioSummaryChange | null
  currencyTotals: { currency: string; marketValue: number | null; missingQuotes: number }[]
}
export interface Portfolios { items: Portfolio[]; valuedAt: string; summary?: PortfolioSummary }
function accountHeaders(owner?: number): Record<string, string> {
  return owner === undefined ? {} : { 'X-Expected-User-Id': String(owner) }
}

export function portfolioRequest<T>(method: string, path = '', body?: unknown, signal?: AbortSignal, owner?: number) {
  return apiFetch<T>(`/api/portfolios${path}`, {
    method, signal, headers: accountHeaders(owner), ...(body === undefined ? {} : { body: JSON.stringify(body) }),
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
export function previewXtb(portfolioId: string, file: File, signal: AbortSignal, owner?: number) {
  return uploadXtb<XtbPreview>(portfolioId, file, signal, owner)
}
export function importXtb(portfolioId: string, file: File, version: number, allowPartial: boolean, signal: AbortSignal, owner?: number) {
  return uploadXtb<XtbImportResult>(portfolioId, file, signal, owner, { version, allowPartial })
}
function uploadXtb<T>(portfolioId: string, file: File, signal: AbortSignal, owner?: number, approval?: { version: number; allowPartial: boolean }) {
  const query = new URLSearchParams({ filename: file.name })
  if (approval) query.set('version', String(approval.version))
  if (approval?.allowPartial) query.set('allow_partial', 'true')
  return apiFetch<T>(`/api/portfolios/${portfolioId}/imports/xtb${approval ? '' : '/preview'}?${query}`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream', ...accountHeaders(owner) }, body: file, signal,
  })
}

export interface XtbWalletPreview extends Omit<XtbPreview, 'version'> {
  id: string; name: string; sheet: string; version: number | null; error: string | null
  reconciliation?: XtbReconciliation | null
}
export interface XtbReconciliation {
  asOf: string
  changes: {
    ticker: string; currency: string
    previousQuantity: string; quantity: string
    previousCost: string; cost: string
  }[]
}
export interface XtbWalletsPreview {
  wallets: XtbWalletPreview[]
  ready: number; errors: number; newWallets: number
  previewToken: string; blockingError: string | null
}
export interface XtbWalletsImportResult {
  wallets: (XtbImportResult & { id: string; name: string })[]
  imported: number; duplicates: number; skipped: number; created: number
}
export function previewXtbWallets(file: File, owner: number, signal: AbortSignal) {
  return uploadXtbWallets<XtbWalletsPreview>(file, owner, signal)
}
export function importXtbWallets(file: File, owner: number, previewToken: string, allowPartial: boolean, signal: AbortSignal) {
  return uploadXtbWallets<XtbWalletsImportResult>(file, owner, signal, { previewToken, allowPartial })
}
function uploadXtbWallets<T>(file: File, owner: number, signal: AbortSignal, approval?: { previewToken: string; allowPartial: boolean }) {
  const query = new URLSearchParams({ filename: file.name })
  if (approval?.allowPartial) query.set('allow_partial', 'true')
  const headers: Record<string, string> = {
    'Content-Type': 'application/octet-stream',
    ...accountHeaders(owner),
  }
  if (approval) headers['X-XTB-Preview'] = approval.previewToken
  return apiFetch<T>(`/api/portfolios/imports/xtb/wallets${approval ? '' : '/preview'}?${query}`, {
    method: 'POST', headers, body: file, signal,
  })
}
