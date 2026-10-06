// Component test for the Volume surge page's surge context (roadmap #15b):
// the report chip, the peak-day reading, the range tag and the signal age.
// The data hooks are mocked, so nothing goes over the network.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, within } from '../test/utils'
import type { ApiVolumeSurgeItem, ApiVolumeSurgeResponse } from '../api/stocksApi'

const { useVolumeSurgeMock } = vi.hoisted(() => ({ useVolumeSurgeMock: vi.fn() }))

vi.mock('../hooks/useVolumeSurge', () => ({ useVolumeSurge: useVolumeSurgeMock }))
vi.mock('../hooks/useMarkets', () => ({
  useMarketScope: () => ({ market: 'gpw', markets: null }),
}))

import { VolumeSurgePage } from './VolumeSurgePage'

function makeItem(over: Partial<ApiVolumeSurgeItem> = {}): ApiVolumeSurgeItem {
  return {
    ticker: 'KGH',
    name: 'KGHM Polska Miedz',
    sector: 'Mining',
    market: 'gpw',
    currency: 'PLN',
    lastPrice: 150,
    recentAvgVolume: 300_000,
    baselineAvgVolume: 100_000,
    volumeRatio: 3,
    lastDayRatio: 3,
    daysAboveBaseline: 3,
    priceChangePct: 4.5,
    currentRating: 70,
    lastSignal: 'Buy',
    daysSinceSignal: 23,
    signalInWindow: false,
    surgeStart: '2026-09-23',
    peakDate: '2026-09-24',
    peakVolumeRatio: 4.2,
    peakChangePct: 3.1,
    peakSpreadRatio: 2,
    peakClosePosition: 0.9,
    breaksHigh: true,
    breaksLow: false,
    reportDate: '2026-09-23',
    ...over,
  }
}

function mockScan(items: ApiVolumeSurgeItem[]) {
  const meta: ApiVolumeSurgeResponse = {
    asOf: '2026-09-25',
    recentDays: 3,
    baselineDays: 20,
    minRatio: 1.5,
    scannedCount: 130,
    totalCount: items.length,
    items,
  }
  useVolumeSurgeMock.mockReturnValue({
    items,
    meta,
    loading: false,
    loadingMore: false,
    error: null,
    hasMore: false,
    refetch: vi.fn(),
  })
}

describe('VolumeSurgePage surge context', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
  })

  it('marks a surge that lines up with a report', () => {
    mockScan([makeItem(), makeItem({ ticker: 'PKO', name: 'PKO BP', reportDate: null })])
    renderWithProviders(<VolumeSurgePage />)
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    // Header + two rows; only KGHM carries the chip.
    expect(within(rows[1]).getByText('REPORT')).toBeInTheDocument()
    expect(within(rows[2]).queryByText('REPORT')).toBeNull()
  })

  it('reads the peak session, the range break and the signal age', () => {
    mockScan([makeItem()])
    renderWithProviders(<VolumeSurgePage />)
    const row = within(screen.getByRole('table')).getAllByRole('row')[1]
    expect(within(row).getByText('Thu 24.09')).toBeInTheDocument()
    expect(within(row).getByText(/Wide, closed high/)).toBeInTheDocument()
    expect(within(row).getByText('↑ 20-session high')).toBeInTheDocument()
    expect(within(row).getByText('last signal 23 d ago')).toBeInTheDocument()
  })

  it('says when the signal belongs to the surge', () => {
    mockScan([
      makeItem({ signalInWindow: true, daysSinceSignal: 1, breaksHigh: false }),
    ])
    renderWithProviders(<VolumeSurgePage />)
    const row = within(screen.getByRole('table')).getAllByRole('row')[1]
    expect(within(row).getByText('signal in the surge')).toBeInTheDocument()
    expect(within(row).queryByText(/20-session/)).toBeNull()
  })

  it('explains the typical-session baseline in the header', () => {
    mockScan([makeItem()])
    renderWithProviders(<VolumeSurgePage />)
    expect(screen.getByText(/their typical/)).toBeInTheDocument()
  })
})
