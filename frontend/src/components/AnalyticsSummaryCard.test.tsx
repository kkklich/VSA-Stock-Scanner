// Component test for the Analytics Summary card. The data hook is mocked so the
// test drives rendering directly, without any network. Covers: the loading and
// error states, and that a populated summary renders the stance, agreement,
// headline, paragraph and one row per source (with the reliability row split
// out).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen } from '../test/utils'
import type { ApiAnalyticsSummary } from '../api/stocksApi'
import type { UseOpinionSummaryResult } from '../hooks/useOpinionSummary'

const { useOpinionSummaryMock } = vi.hoisted(() => ({
  useOpinionSummaryMock: vi.fn(),
}))

vi.mock('../hooks/useOpinionSummary', () => ({
  useOpinionSummary: useOpinionSummaryMock,
}))

// Import after the mock is registered.
import { AnalyticsSummaryCard } from './AnalyticsSummaryCard'

const SUMMARY: ApiAnalyticsSummary = {
  ticker: 'KGH',
  name: 'KGHM',
  asOf: '2026-09-01',
  stance: 'bullish',
  agreement: 80,
  headline: 'The signals broadly agree — KGHM looks bullish.',
  summary: 'The VSA engine reads KGHM as Buy while the AI Insight says Buy.',
  sources: [
    {
      key: 'vsa',
      label: 'VSA rating',
      kind: 'direction',
      stance: 'bullish',
      headline: 'Buy · 72/100',
      detail: 'VSA rates this stock 72/100.',
      firedRecently: true,
    },
    {
      key: 'minervini',
      label: 'Minervini Trend Template',
      kind: 'direction',
      stance: 'neutral',
      headline: '4/7 rules · 57/100',
      detail: 'Minervini scores 57/100.',
      firedRecently: false,
    },
    {
      key: 'trustScore',
      label: 'Signal Trust Score',
      kind: 'reliability',
      stance: 'bullish',
      headline: 'Reliable · 71/100',
      detail: "The engine's past strong calls have been reliable.",
      firedRecently: false,
    },
  ],
  engine: 'stockpilot-summary-1',
}

function result(over: Partial<UseOpinionSummaryResult> = {}): UseOpinionSummaryResult {
  return { data: SUMMARY, loading: false, error: null, ...over }
}

beforeEach(() => {
  useOpinionSummaryMock.mockReturnValue(result())
})

describe('AnalyticsSummaryCard', () => {
  it('renders the stance, agreement, headline and every source row', () => {
    renderWithProviders(<AnalyticsSummaryCard ticker="kgh" />)

    expect(screen.getByText('Analytics summary')).toBeInTheDocument()
    expect(screen.getByText('Bullish')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText(/broadly agree/i)).toBeInTheDocument()

    // One row per source, including the split-out reliability row.
    expect(screen.getByText('VSA rating')).toBeInTheDocument()
    expect(screen.getByText('Minervini Trend Template')).toBeInTheDocument()
    expect(screen.getByText('Signal Trust Score')).toBeInTheDocument()
    expect(screen.getByText('Buy · 72/100')).toBeInTheDocument()

    // The "fired recently" chip shows only for the VSA row.
    expect(screen.getByText('Fired')).toBeInTheDocument()
  })

  it('shows the loading state while the summary loads', () => {
    useOpinionSummaryMock.mockReturnValue(result({ data: null, loading: true }))
    renderWithProviders(<AnalyticsSummaryCard ticker="kgh" />)
    expect(screen.getByText(/Summarising/i)).toBeInTheDocument()
  })

  it('shows an error message when the fetch fails', () => {
    useOpinionSummaryMock.mockReturnValue(result({ data: null, error: 'boom' }))
    renderWithProviders(<AnalyticsSummaryCard ticker="kgh" />)
    expect(screen.getByText(/Summary unavailable: boom/i)).toBeInTheDocument()
  })
})
