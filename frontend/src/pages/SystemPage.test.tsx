// The System page answers "did last night's refresh run?". These tests guard
// the answers that matter operationally: a missed run must read as missed (not
// as a blank card), a failure must show its reason, errors must appear grouped
// with their count, and an unguarded admin API must say so.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, waitFor } from '../test/utils'
import { SystemPage } from './SystemPage'
import type { ApiSystemHealth } from '../api/adminApi'
import * as adminApi from '../api/adminApi'
import i18n from '../i18n'

const HEALTHY: ApiSystemHealth = {
  asOf: '2026-09-08T10:00:00+00:00',
  asOfLocal: '2026-09-08T12:00:00+02:00',
  status: 'ok',
  version: '1.0.0',
  uptimeSeconds: 7200,
  protected: true,
  ingest: {
    status: 'ok',
    summary: 'Last refresh finished 17.9 h ago.',
    running: false,
    lastRunAt: '2026-09-07T16:05:00+00:00',
    lastRunLocal: '2026-09-07T18:05:00+02:00',
    lastOutcome: 'finished',
    lastTrigger: 'nightly',
    durationMs: 92_000,
    ageHours: 17.9,
    lastSuccessAt: '2026-09-07T16:05:00+00:00',
    lastSuccessLocal: '2026-09-07T18:05:00+02:00',
    lastError: null,
    stocksRanked: 126,
    fetched: 288,
    skipped: 2,
    failed: 0,
    barsWritten: 1440,
    expectedAt: '2026-09-07T16:00:00+00:00',
    expectedLocal: '2026-09-07T18:00:00+02:00',
    ranSinceExpected: true,
    nextRunAt: '2026-09-08T16:00:00+00:00',
    nextRunLocal: '2026-09-08T18:00:00+02:00',
    schedulerActive: true,
    schedule: '18:00 Europe/Warsaw',
  },
  data: {
    status: 'ok',
    summary: '288 of 288 companies are current.',
    dbEnabled: true,
    latestBarDate: '2026-09-08',
    earliestBarDate: '2024-01-02',
    latestSnapshotDate: '2026-09-08',
    sessionAgeDays: 0,
    tickersTracked: 288,
    tickersWithData: 288,
    tickersCurrent: 288,
    tickersBehind: 0,
    coveragePct: 100,
    barCount: 120_000,
  },
  errors: {
    status: 'ok',
    summary: 'No errors.',
    windowHours: 24,
    totalCount: 0,
    groupCount: 0,
    top: [],
  },
  log: {
    enabled: true,
    filePath: 'D:/app/logs/actions.jsonl',
    dbActive: true,
    recordedCount: 4210,
    dbWrittenCount: 4180,
    droppedCount: 0,
  },
}

const EMPTY_ERRORS = {
  asOf: HEALTHY.asOf,
  source: 'database',
  windowHours: 24,
  totalCount: 0,
  groupCount: 0,
  trackedSince: HEALTHY.asOf,
  items: [],
}

const EMPTY_LOGS = {
  source: 'database',
  totalCount: 0,
  page: 1,
  pageSize: 25,
  items: [],
}

function mock(health: ApiSystemHealth, errors = EMPTY_ERRORS) {
  vi.spyOn(adminApi, 'fetchSystemHealth').mockResolvedValue(health)
  vi.spyOn(adminApi, 'fetchErrors').mockResolvedValue(errors)
  vi.spyOn(adminApi, 'fetchActionLogs').mockResolvedValue(EMPTY_LOGS)
}

beforeEach(async () => {
  await i18n.changeLanguage('en')
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SystemPage', () => {
  it('reports a refresh that ran, with what it fetched', async () => {
    mock(HEALTHY)
    renderWithProviders(<SystemPage />)

    expect(
      await screen.findByText(
        'The last refresh finished 17.9 h ago and fetched 288 companies.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    // The counters that say the run did real work.
    expect(screen.getByText('1440')).toBeInTheDocument()
  })

  it('says plainly when the nightly job did not run', async () => {
    mock({
      ...HEALTHY,
      status: 'warn',
      ingest: {
        ...HEALTHY.ingest,
        status: 'stale',
        ranSinceExpected: false,
        lastSuccessAt: '2026-09-05T16:05:00+00:00',
      },
    })
    renderWithProviders(<SystemPage />)

    expect(await screen.findByText('Did not run')).toBeInTheDocument()
    expect(screen.getByText(/Nothing ran when the refresh came due/)).toBeInTheDocument()
  })

  it('shows the reason a refresh failed', async () => {
    mock({
      ...HEALTHY,
      status: 'error',
      ingest: {
        ...HEALTHY.ingest,
        status: 'failed',
        lastOutcome: 'failed',
        lastError: 'ConnectionError: yahoo unreachable',
      },
    })
    renderWithProviders(<SystemPage />)

    expect(
      await screen.findByText(
        'The last refresh failed: ConnectionError: yahoo unreachable',
      ),
    ).toBeInTheDocument()
  })

  it('lists errors grouped, with how often each happened', async () => {
    mock(HEALTHY, {
      ...EMPTY_ERRORS,
      totalCount: 290,
      groupCount: 1,
      items: [
        {
          fingerprint: 'abc123',
          errorType: 'StooqAccessError',
          message: 'Ingest error for %s: %s',
          lastMessage: 'Ingest error for kgh: timeout',
          where: 'jobs/daily_ingest.py:179 in ingest_one',
          source: 'app.jobs.daily_ingest',
          count: 290,
          firstSeen: HEALTHY.asOf,
          lastSeen: HEALTHY.asOf,
          lastSeenLocal: HEALTHY.asOfLocal,
          traceback: null,
          context: null,
        },
      ],
    })
    renderWithProviders(<SystemPage />)

    // One row for 290 failures — the point of grouping.
    expect(await screen.findByText('×290')).toBeInTheDocument()
    expect(screen.getByText('StooqAccessError')).toBeInTheDocument()
    expect(screen.getByText('Ingest error for kgh: timeout')).toBeInTheDocument()
  })

  it('warns when the admin API has no token configured', async () => {
    mock({ ...HEALTHY, protected: false })
    renderWithProviders(<SystemPage />)

    expect(
      await screen.findByText(/The admin API has no token configured/),
    ).toBeInTheDocument()
  })

  it('asks for a token instead of an error when the API rejects the call', async () => {
    const { ApiError } = await import('../api/client')
    vi.spyOn(adminApi, 'fetchSystemHealth').mockRejectedValue(
      new ApiError(401, 'Admin token required.'),
    )
    vi.spyOn(adminApi, 'fetchErrors').mockResolvedValue(EMPTY_ERRORS)
    vi.spyOn(adminApi, 'fetchActionLogs').mockResolvedValue(EMPTY_LOGS)

    renderWithProviders(<SystemPage />)

    expect(
      await screen.findByText(/The admin API requires a token/),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Admin token')).toBeInTheDocument()
  })

  it('is translated — the Polish UI shows no English fallback', async () => {
    mock(HEALTHY)
    renderWithProviders(<SystemPage />)
    await screen.findByText('Healthy')

    await i18n.changeLanguage('pl')
    await waitFor(() => expect(screen.getByText('W porządku')).toBeInTheDocument())
    expect(screen.getByText('Odświeżanie danych')).toBeInTheDocument()
  })
})
