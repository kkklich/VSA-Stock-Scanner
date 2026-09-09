// Typed API calls for the /api/admin/* endpoints — the System page.
// Shapes mirror the Pydantic models in backend-python/app/models/admin.py.
//
// These endpoints are the app watching itself: did the nightly refresh run,
// is the stored data current, what has been failing, and what has the app been
// doing. They are optionally protected by a shared secret
// (STOCKPILOT_ADMIN_TOKEN on the backend); when one is configured every call
// must carry it in an `X-Admin-Token` header — see lib/adminToken.ts.

import { apiFetch } from './client'
import { getAdminToken } from '../lib/adminToken'

/** The token header, when the user has stored one. Omitted otherwise, which is
 *  correct for a backend that has no token configured (the local default). */
function authHeaders(): HeadersInit | undefined {
  const token = getAdminToken()
  return token ? { 'X-Admin-Token': token } : undefined
}

function get<T>(path: string): Promise<T> {
  const headers = authHeaders()
  return apiFetch<T>(path, headers ? { headers } : undefined)
}

// ── GET /api/admin/health ─────────────────────────────────────────────────────

/** Worst-of read for the whole app, and for each section. */
export type HealthStatus = 'ok' | 'warn' | 'error'
/** Ingest verdicts. `stale` = the scheduled run came due and nothing happened. */
export type IngestStatus = 'ok' | 'running' | 'stale' | 'failed' | 'never'
export type DataStatus =
  | 'ok'
  /** A refresh is working through the universe: partial coverage is the run. */
  | 'updating'
  | 'stale'
  | 'empty'
  | 'disabled'
  | 'error'

export interface ApiIngestHealth {
  status: IngestStatus
  summary: string
  running: boolean
  lastRunAt: string | null
  lastRunLocal: string | null
  lastOutcome: string | null
  lastTrigger: string | null
  durationMs: number | null
  ageHours: number | null
  lastSuccessAt: string | null
  lastSuccessLocal: string | null
  lastError: string | null
  stocksRanked: number | null
  fetched: number | null
  skipped: number | null
  failed: number | null
  barsWritten: number | null
  expectedAt: string | null
  expectedLocal: string | null
  ranSinceExpected: boolean | null
  nextRunAt: string | null
  nextRunLocal: string | null
  schedulerActive: boolean
  schedule: string
}

export interface ApiDataHealth {
  status: DataStatus
  summary: string
  dbEnabled: boolean
  latestBarDate: string | null
  earliestBarDate: string | null
  latestSnapshotDate: string | null
  sessionAgeDays: number | null
  tickersTracked: number
  tickersWithData: number | null
  tickersCurrent: number | null
  tickersBehind: number | null
  coveragePct: number | null
  barCount: number | null
}

/** One *kind* of error, with how often it has happened. */
export interface ApiErrorGroup {
  fingerprint: string
  errorType: string
  /** The message template — the group's identity. */
  message: string
  /** The newest fully substituted message. */
  lastMessage: string | null
  where: string | null
  source: string | null
  count: number
  firstSeen: string
  lastSeen: string
  lastSeenLocal: string
  traceback: string | null
  context: Record<string, unknown> | null
}

export interface ApiErrorHealth {
  status: HealthStatus
  summary: string
  windowHours: number
  totalCount: number
  groupCount: number
  top: ApiErrorGroup[]
}

export interface ApiLogHealth {
  enabled: boolean
  filePath: string | null
  dbActive: boolean
  recordedCount: number
  dbWrittenCount: number
  droppedCount: number
}

export interface ApiSystemHealth {
  asOf: string
  asOfLocal: string
  status: HealthStatus
  version: string
  uptimeSeconds: number
  /** False when the admin API is reachable without a token — the page warns. */
  protected: boolean
  ingest: ApiIngestHealth
  data: ApiDataHealth
  errors: ApiErrorHealth
  log: ApiLogHealth
}

export function fetchSystemHealth(): Promise<ApiSystemHealth> {
  return get<ApiSystemHealth>('/api/admin/health')
}

// ── GET /api/admin/errors ─────────────────────────────────────────────────────

export interface ApiErrorList {
  asOf: string
  /** "database" (survives restarts) or "memory" (this process only). */
  source: string
  windowHours: number
  totalCount: number
  groupCount: number
  trackedSince: string | null
  items: ApiErrorGroup[]
}

export function fetchErrors(hours = 24, limit = 50): Promise<ApiErrorList> {
  return get<ApiErrorList>(`/api/admin/errors?hours=${hours}&limit=${limit}`)
}

// ── GET /api/admin/logs ───────────────────────────────────────────────────────

export interface ApiActionLogItem {
  timestamp: string
  timestampLocal: string
  requestId: string
  kind: 'request' | 'job' | 'error'
  action: string
  outcome: string
  durationMs: number | null
  method: string | null
  path: string | null
  query: string | null
  statusCode: number | null
  responseBytes: number | null
  clientIp: string | null
  userAgent: string | null
  detail: Record<string, unknown> | null
}

export interface ApiActionLogResponse {
  source: string
  totalCount: number
  page: number
  pageSize: number
  items: ApiActionLogItem[]
}

export interface ActionLogQuery {
  kind?: 'request' | 'job' | 'error'
  outcome?: string
  action?: string
  page?: number
  pageSize?: number
}

export function fetchActionLogs(query: ActionLogQuery = {}): Promise<ApiActionLogResponse> {
  const params = new URLSearchParams()
  if (query.kind) params.set('kind', query.kind)
  if (query.outcome) params.set('outcome', query.outcome)
  if (query.action) params.set('action', query.action)
  params.set('page', String(query.page ?? 1))
  params.set('pageSize', String(query.pageSize ?? 25))
  return get<ApiActionLogResponse>(`/api/admin/logs?${params.toString()}`)
}
