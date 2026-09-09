// System page — the app watching itself.
//
// It exists to answer one question without anyone opening a terminal: **did
// last night's data refresh actually run?** A background job is accepted with a
// 202 and then reports to nobody, so a run that quietly fetched nothing used to
// look exactly like a run that worked.
//
// Four readings, in the order they matter:
//   1. Data refresh — the last job.refresh / job.ingest outcome, measured
//      against the scheduled 18:00 Warsaw run.
//   2. Stored data — what is actually in the database, independent of what the
//      job claimed: newest session, how many companies have it.
//   3. Errors — grouped, so 290 failing tickers read as one problem seen 290
//      times rather than 290 separate rows.
//   4. Action log — the recent timeline, filterable.
//
// Everything comes from GET /api/admin/{health,errors,logs}. Those endpoints
// carry stack traces and visitor IP addresses, so the page says out loud when
// the backend has no admin token configured, and takes one when it has.

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Clock,
  Database,
  KeyRound,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldAlert,
  XCircle,
} from 'lucide-react'
import type {
  ApiErrorGroup,
  ApiSystemHealth,
  HealthStatus,
} from '../api/adminApi'
import { getAdminToken, setAdminToken } from '../lib/adminToken'
import {
  useActionLogs,
  useErrorGroups,
  useSystemHealth,
} from '../hooks/useSystemStatus'

// ── Small shared pieces ───────────────────────────────────────────────────────

const TONE: Record<HealthStatus, { chip: string; text: string; Icon: typeof CheckCircle2 }> = {
  ok: {
    chip: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
    text: 'text-emerald-400',
    Icon: CheckCircle2,
  },
  warn: {
    chip: 'bg-amber-500/15 text-amber-400 ring-amber-500/30',
    text: 'text-amber-400',
    Icon: AlertTriangle,
  },
  error: {
    chip: 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
    text: 'text-rose-400',
    Icon: XCircle,
  },
}

/** Section verdicts map onto the three colours the whole app already uses. */
function toneOf(status: string): HealthStatus {
  if (status === 'failed' || status === 'error') return 'error'
  if (['ok', 'running', 'updating', 'disabled'].includes(status)) return 'ok'
  return 'warn'
}

function StatusChip({ status, label }: { status: HealthStatus; label: string }) {
  const { chip, Icon } = TONE[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${chip}`}
    >
      <Icon size={13} />
      {label}
    </span>
  )
}

function Card({
  title,
  icon: Icon,
  status,
  statusLabel,
  children,
}: {
  title: string
  icon: typeof Activity
  status?: HealthStatus
  statusLabel?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 sm:p-5">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <Icon size={16} className="text-slate-500" />
          {title}
        </h2>
        {status && statusLabel && <StatusChip status={status} label={statusLabel} />}
      </header>
      {children}
    </section>
  )
}

/** One label/value pair. Values are the point, so they get the stronger ink. */
function Fact({
  label,
  value,
  tone = '',
}: {
  label: string
  value: React.ReactNode
  tone?: string
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`truncate text-sm font-medium text-slate-200 ${tone}`}>
        {value}
      </div>
    </div>
  )
}

const DASH = '—'

/** Local timestamp, second precision dropped: these are human-scale events. */
function fmtMoment(iso: string | null): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  return d.toLocaleString('pl-PL', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function fmtDuration(ms: number | null): string {
  if (ms == null) return DASH
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`
}

const fmtInt = (n: number | null | undefined): string =>
  n == null ? DASH : n.toLocaleString('pl-PL')

// ── Ingest ────────────────────────────────────────────────────────────────────

function IngestCard({ health }: { health: ApiSystemHealth }) {
  const { t } = useTranslation()
  const ingest = health.ingest
  const tone = toneOf(ingest.status)

  // Localised in the UI rather than taken from the payload: the backend sends
  // an English `summary` for API callers, but this page is bilingual.
  const summary = (() => {
    switch (ingest.status) {
      case 'running':
        return t('system.ingest.summaryRunning')
      case 'never':
        return ingest.schedulerActive
          ? t('system.ingest.summaryNever')
          : t('system.ingest.summaryNoScheduler')
      case 'failed':
        return t('system.ingest.summaryFailed', {
          error: ingest.lastError ?? DASH,
        })
      case 'stale':
        return t('system.ingest.summaryStale', {
          expected: fmtMoment(ingest.expectedAt),
          last: fmtMoment(ingest.lastSuccessAt),
        })
      default:
        return t('system.ingest.summaryOk', {
          hours: (ingest.ageHours ?? 0).toFixed(1),
          fetched: fmtInt(ingest.fetched),
        })
    }
  })()

  return (
    <Card
      title={t('system.ingest.title')}
      icon={RefreshCw}
      status={tone}
      statusLabel={t(`system.ingest.status.${ingest.status}`)}
    >
      <p className={`mb-4 text-sm leading-relaxed ${TONE[tone].text}`}>{summary}</p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <Fact label={t('system.ingest.lastRun')} value={fmtMoment(ingest.lastRunAt)} />
        <Fact
          label={t('system.ingest.duration')}
          value={fmtDuration(ingest.durationMs)}
        />
        <Fact
          label={t('system.ingest.trigger')}
          value={ingest.lastTrigger ?? DASH}
        />
        <Fact
          label={t('system.ingest.nextRun')}
          value={
            ingest.schedulerActive
              ? fmtMoment(ingest.nextRunAt) || ingest.schedule
              : t('system.ingest.noScheduler')
          }
        />
        <Fact label={t('system.ingest.fetched')} value={fmtInt(ingest.fetched)} />
        <Fact label={t('system.ingest.skipped')} value={fmtInt(ingest.skipped)} />
        <Fact
          label={t('system.ingest.failed')}
          value={fmtInt(ingest.failed)}
          tone={ingest.failed ? 'text-rose-400' : ''}
        />
        <Fact label={t('system.ingest.bars')} value={fmtInt(ingest.barsWritten)} />
      </div>

      {ingest.lastError && ingest.status !== 'failed' && (
        <p className="mt-4 rounded-lg bg-slate-800/50 p-3 font-mono text-xs text-rose-400">
          {ingest.lastError}
        </p>
      )}
    </Card>
  )
}

// ── Stored data ───────────────────────────────────────────────────────────────

function DataCard({ health }: { health: ApiSystemHealth }) {
  const { t } = useTranslation()
  const data = health.data
  const tone = toneOf(data.status)

  const summary = (() => {
    switch (data.status) {
      case 'disabled':
        return t('system.data.summaryDisabled')
      case 'error':
        return t('system.data.summaryError')
      case 'empty':
        return t('system.data.summaryEmpty')
      case 'updating':
        return t('system.data.summaryUpdating', {
          current: fmtInt(data.tickersCurrent),
          tracked: fmtInt(data.tickersTracked),
          date: data.latestBarDate ?? DASH,
        })
      case 'stale':
        return t('system.data.summaryStale', {
          date: data.latestBarDate ?? DASH,
          days: data.sessionAgeDays ?? 0,
          current: fmtInt(data.tickersCurrent),
          tracked: fmtInt(data.tickersTracked),
        })
      default:
        return t('system.data.summaryOk', {
          current: fmtInt(data.tickersCurrent),
          tracked: fmtInt(data.tickersTracked),
          date: data.latestBarDate ?? DASH,
        })
    }
  })()

  return (
    <Card
      title={t('system.data.title')}
      icon={Database}
      status={tone}
      statusLabel={t(`system.data.status.${data.status}`)}
    >
      <p className={`mb-4 text-sm leading-relaxed ${TONE[tone].text}`}>{summary}</p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <Fact
          label={t('system.data.latestSession')}
          value={data.latestBarDate ?? DASH}
        />
        <Fact
          label={t('system.data.coverage')}
          value={
            data.coveragePct == null
              ? DASH
              : `${data.coveragePct}% (${fmtInt(data.tickersCurrent)}/${fmtInt(
                  data.tickersTracked,
                )})`
          }
        />
        <Fact
          label={t('system.data.historyFrom')}
          value={data.earliestBarDate ?? DASH}
        />
        <Fact label={t('system.data.bars')} value={fmtInt(data.barCount)} />
        <Fact
          label={t('system.data.snapshots')}
          value={data.latestSnapshotDate ?? DASH}
        />
        <Fact
          label={t('system.data.behind')}
          value={fmtInt(data.tickersBehind)}
          tone={data.tickersBehind ? 'text-amber-400' : ''}
        />
      </div>
    </Card>
  )
}

// ── Errors ────────────────────────────────────────────────────────────────────

function ErrorRow({ group }: { group: ApiErrorGroup }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <li className="rounded-lg border border-slate-800 bg-slate-800/30 p-3">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 shrink-0 rounded-md bg-rose-500/15 px-2 py-0.5 text-xs font-semibold text-rose-400 ring-1 ring-inset ring-rose-500/30">
          ×{group.count}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-semibold text-slate-200">
              {group.errorType}
            </span>
            <span className="text-xs text-slate-500">{group.source}</span>
          </div>
          <p className="mt-0.5 break-words text-sm text-slate-300">
            {group.lastMessage || group.message}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            {group.where && <span className="font-mono">{group.where}</span>}
            <span>
              {t('system.errors.lastSeen')} {fmtMoment(group.lastSeen)}
            </span>
            {group.traceback && (
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-slate-400 hover:text-slate-200"
              >
                <ChevronDown
                  size={12}
                  className={open ? 'rotate-180 transition-transform' : 'transition-transform'}
                />
                {open ? t('system.errors.hideTrace') : t('system.errors.showTrace')}
              </button>
            )}
          </div>
          {open && group.traceback && (
            <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-950/70 p-3 text-[11px] leading-relaxed text-slate-400">
              {group.traceback}
            </pre>
          )}
        </div>
      </div>
    </li>
  )
}

function ErrorsCard({ refreshToken }: { refreshToken?: unknown }) {
  const { t } = useTranslation()
  const { data, loading, error } = useErrorGroups(24, refreshToken)

  const tone: HealthStatus = !data || data.totalCount === 0 ? 'ok' : 'warn'

  return (
    <Card
      title={t('system.errors.title')}
      icon={ShieldAlert}
      status={tone}
      statusLabel={
        data && data.totalCount > 0
          ? t('system.errors.chipSome', { count: data.totalCount })
          : t('system.errors.chipNone')
      }
    >
      {loading && !data ? (
        <p className="text-sm text-slate-500">{t('common.loading')}</p>
      ) : error ? (
        <p className="text-sm text-rose-400">{error}</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-slate-500">
          {t('system.errors.none', { hours: data?.windowHours ?? 24 })}
        </p>
      ) : (
        <>
          <p className="mb-3 text-xs text-slate-500">
            {t('system.errors.intro', {
              count: data.totalCount,
              groups: data.groupCount,
              hours: data.windowHours,
            })}{' '}
            {t(
              data.source === 'database'
                ? 'system.errors.sourceDatabase'
                : 'system.errors.sourceMemory',
            )}
          </p>
          <ul className="space-y-2">
            {data.items.map((group) => (
              <ErrorRow key={group.fingerprint} group={group} />
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

// ── Action log ────────────────────────────────────────────────────────────────

const OUTCOME_TONE: Record<string, string> = {
  ok: 'text-emerald-400',
  finished: 'text-emerald-400',
  started: 'text-slate-400',
  skipped: 'text-slate-400',
  client_error: 'text-amber-400',
  server_error: 'text-rose-400',
  failed: 'text-rose-400',
}

function ActionLogCard({ refreshToken }: { refreshToken?: unknown }) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<'' | 'request' | 'job' | 'error'>('')
  const { data, loading, error } = useActionLogs(
    { kind: kind || undefined, pageSize: 25 },
    refreshToken,
  )

  return (
    <Card title={t('system.log.title')} icon={ScrollText}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {(['', 'job', 'request', 'error'] as const).map((option) => (
          <button
            key={option || 'all'}
            type="button"
            onClick={() => setKind(option)}
            className={
              'rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ' +
              (kind === option
                ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-inset ring-emerald-500/30'
                : 'bg-slate-800/60 text-slate-400 hover:text-slate-200')
            }
          >
            {t(`system.log.kind.${option || 'all'}`)}
          </button>
        ))}
        {data && (
          <span className="ml-auto text-xs text-slate-500">
            {t('system.log.total', { count: data.totalCount })}
          </span>
        )}
      </div>

      {loading && !data ? (
        <p className="text-sm text-slate-500">{t('common.loading')}</p>
      ) : error ? (
        <p className="text-sm text-rose-400">{error}</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-slate-500">{t('system.log.empty')}</p>
      ) : (
        <div className="-mx-4 overflow-x-auto sm:-mx-5">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2 font-medium sm:px-5">{t('system.log.time')}</th>
                <th className="px-2 py-2 font-medium">{t('system.log.action')}</th>
                <th className="px-2 py-2 font-medium">{t('system.log.outcome')}</th>
                <th className="px-2 py-2 text-right font-medium">
                  {t('system.log.duration')}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr
                  key={item.requestId + item.timestamp}
                  className="border-b border-slate-800/60 last:border-0"
                >
                  <td className="whitespace-nowrap px-4 py-2 text-slate-400 sm:px-5">
                    {fmtMoment(item.timestampLocal)}
                  </td>
                  <td className="max-w-[280px] truncate px-2 py-2 text-slate-300">
                    <span className="font-mono text-xs">{item.action}</span>
                  </td>
                  <td
                    className={`whitespace-nowrap px-2 py-2 text-xs font-medium ${
                      OUTCOME_TONE[item.outcome] ?? 'text-slate-400'
                    }`}
                  >
                    {item.outcome}
                    {item.statusCode ? ` (${item.statusCode})` : ''}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-right text-slate-400">
                    {fmtDuration(item.durationMs)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ── Access (the admin token) ──────────────────────────────────────────────────

function AccessCard({
  unprotected,
  onSaved,
}: {
  unprotected: boolean
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const [token, setToken] = useState(getAdminToken())
  const [saved, setSaved] = useState(false)

  return (
    <Card title={t('system.access.title')} icon={KeyRound}>
      <p className="mb-3 text-xs leading-relaxed text-slate-500">
        {t('system.access.hint')}
      </p>
      {unprotected && (
        <p className="mb-3 flex items-start gap-2 rounded-lg bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-400 ring-1 ring-inset ring-amber-500/20">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          {t('system.access.openWarning')}
        </p>
      )}
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setAdminToken(token)
          setSaved(true)
          onSaved()
        }}
      >
        <input
          type="password"
          value={token}
          onChange={(e) => {
            setToken(e.target.value)
            setSaved(false)
          }}
          placeholder={t('system.access.tokenPlaceholder')}
          aria-label={t('system.access.tokenLabel')}
          className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-800/50 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-emerald-500/50 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-lg bg-slate-800 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700"
        >
          {saved ? t('system.access.saved') : t('system.access.save')}
        </button>
      </form>
    </Card>
  )
}

// ── The page ──────────────────────────────────────────────────────────────────

export function SystemPage() {
  const { t } = useTranslation()
  const { data: health, loading, error, unauthorized, reload } = useSystemHealth()

  return (
    <div className="flex flex-col gap-4 p-4 sm:gap-5 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-slate-100">
            {t('system.title')}
            {health && (
              <StatusChip
                status={health.status}
                label={t(`system.status.${health.status}`)}
              />
            )}
          </h1>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500">
            {t('system.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {health && (
            <span className="hidden items-center gap-1.5 text-xs text-slate-500 sm:flex">
              <Clock size={12} />
              {t('system.lastChecked', { time: fmtMoment(health.asOf) })}
            </span>
          )}
          <button
            type="button"
            onClick={reload}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            {t('system.refreshNow')}
          </button>
        </div>
      </header>

      {unauthorized ? (
        <>
          <p className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-400">
            {t('system.access.unauthorized')}
          </p>
          <AccessCard unprotected={false} onSaved={reload} />
        </>
      ) : error && !health ? (
        <p className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-400">
          {error}
        </p>
      ) : !health ? (
        <p className="text-sm text-slate-500">{t('common.loading')}</p>
      ) : (
        <>
          <IngestCard health={health} />
          <DataCard health={health} />
          {/* `asOf` changes on every health read, so one button and one poll
              refresh all three cards instead of only the first. */}
          <ErrorsCard refreshToken={health.asOf} />
          <ActionLogCard refreshToken={health.asOf} />

          <Card title={t('system.log.healthTitle')} icon={Activity}>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Fact
                label={t('system.log.storage')}
                value={t(
                  health.log.dbActive
                    ? 'system.log.storageDatabase'
                    : 'system.log.storageMemory',
                )}
              />
              <Fact
                label={t('system.log.recorded')}
                value={fmtInt(health.log.recordedCount)}
              />
              <Fact
                label={t('system.log.dropped')}
                value={fmtInt(health.log.droppedCount)}
                tone={health.log.droppedCount ? 'text-amber-400' : ''}
              />
              <Fact
                label={t('system.version')}
                value={`${health.version} · ${Math.floor(
                  health.uptimeSeconds / 3600,
                )} h`}
              />
            </div>
            {health.log.filePath && (
              <p className="mt-3 break-all font-mono text-[11px] text-slate-500">
                {health.log.filePath}
              </p>
            )}
          </Card>

          <AccessCard unprotected={!health.protected} onSaved={reload} />
        </>
      )}
    </div>
  )
}
