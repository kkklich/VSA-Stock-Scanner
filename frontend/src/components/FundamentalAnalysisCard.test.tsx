import { afterEach, describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, within } from '../test/utils'
import i18n from '../i18n'
import type { FundamentalAssessment } from '../types/longTerm'
import { FundamentalAnalysisCard } from './FundamentalAnalysisCard'

export const assessment: FundamentalAssessment = {
  modelVersion: 'fundamentals-v1', profile: 'corporate', score: 73,
  pillars: { profitability: 80, growth: 70, cashflow: 60, debt: 65, valuation: 90 },
  inputs: { roe: 0.2, netDebtToEbitda: 2.25, cashConversion: 0.8, fcfYield: null },
  metricScores: { roe: 80, netDebtToEbitda: 65 }, coverage: 85,
  missing: [], warnings: ['weak_cash_conversion'], notApplicable: [],
  comparisonGroup: 'sector', peerCount: 12,
  latestPeriodEnd: '2026-06-30', annualPeriodEnd: '2025-12-31',
}

afterEach(async () => { await i18n.changeLanguage('en') })

describe('Fundamental assessment', () => {
  it('shows all five pillars, financial periods and risks alongside the total', async () => {
    renderWithProviders(<FundamentalAnalysisCard analysis={assessment} />)
    expect(screen.getByRole('region', { name: 'Fundamental assessment' })).toBeVisible()
    expect(screen.getAllByRole('meter')).toHaveLength(5)
    expect(screen.getByText('2026-06-30')).toBeVisible()
    expect(screen.getByText('2025-12-31')).toBeVisible()
    expect(screen.getByText(/Operating cash flow is below net income/)).toBeVisible()
    await userEvent.click(screen.getByText('Show inputs and metric scores'))
    expect(screen.getByText('20%')).toBeVisible()
    expect(screen.getByText('2.25×')).toBeVisible()
    expect(screen.getByText('0.8×')).toBeVisible()
    expect(screen.getByText('Score: 80 / 100')).toBeVisible()
    expect(screen.getByText('—')).toBeVisible()
  })

  it('does not invent meters or a total when evidence is missing', () => {
    renderWithProviders(<FundamentalAnalysisCard analysis={{ ...assessment, score: null,
      pillars: { profitability: 80, growth: null, cashflow: null, debt: 65, valuation: 90 },
      missing: ['growth_missing', 'cashflow_missing', 'peers_missing'] }} />)
    expect(screen.getAllByRole('meter')).toHaveLength(3)
    expect(screen.getAllByRole('img')).toHaveLength(2)
    expect(screen.getByText(/Comparable growth evidence unavailable/)).toBeVisible()
    expect(screen.queryByText(/fundamentals\.missing\./)).not.toBeInTheDocument()
  })

  it('explains the limited bank profile and inapplicable pillars in Polish', async () => {
    await i18n.changeLanguage('pl')
    renderWithProviders(<FundamentalAnalysisCard analysis={{ ...assessment, profile: 'bank',
      pillars: { profitability: 80, growth: 70, valuation: 90 }, notApplicable: ['cashflow', 'debt'],
      warnings: ['limited_financial_profile'] }} />)
    const region = screen.getByRole('region', { name: 'Ocena fundamentalna' })
    expect(within(region).getByText(/Bank · fundamentals-v1/)).toBeVisible()
    expect(screen.getAllByRole('meter')).toHaveLength(3)
    expect(screen.getByText(/Nie stosujemy dla tego profilu/)).toBeVisible()
    expect(screen.getByText(/Nie obejmuje adekwatności kapitałowej banków/)).toBeVisible()
  })
})
