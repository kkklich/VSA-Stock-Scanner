import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../test/utils'
import { InsiderActivityCard } from './InsiderActivityCard'
import type { ApiInsiderTransactionsResponse } from '../api/stocksApi'

const SAMPLE_DATA: ApiInsiderTransactionsResponse = {
  ticker: 'PKO',
  name: 'PKO BP',
  market: 'gpw',
  currency: 'PLN',
  summary: {
    totalPurchasesCount: 2,
    totalSalesCount: 1,
    totalPurchasesShares: 15000,
    totalSalesShares: 2000,
    totalPurchasesValue: 750000,
    totalSalesValue: 110000,
    netShares: 13000,
    netValue: 640000,
    currency: 'PLN',
  },
  transactions: [
    {
      id: 1,
      tradeDate: '2026-04-01',
      publicationDate: '2026-04-02',
      insiderName: 'Jan Kowalski',
      role: 'Prezes Zarządu',
      transactionType: 'buy',
      isOpenMarket: true,
      shares: 15000,
      price: 50,
      currency: 'PLN',
      value: 750000,
      source: 'espi',
      sourceUrl: 'https://www.gpw.pl/espi-ebi-report?geru_id=481001',
      notes: 'MAR Art. 19',
    },
    {
      id: 2,
      tradeDate: '2026-04-05',
      publicationDate: '2026-04-06',
      insiderName: 'Piotr Wiśniewski',
      role: 'Członek Rady Nadzorczej',
      transactionType: 'sell',
      isOpenMarket: true,
      shares: 2000,
      price: 55,
      currency: 'PLN',
      value: 110000,
      source: 'espi',
      sourceUrl: 'https://www.gpw.pl/espi-ebi-report?geru_id=481002',
      notes: 'MAR Art. 19',
    },
  ],
  chartMarkers: [
    {
      date: '2026-04-02',
      type: 'Bullish',
      label: 'INS +15k',
      shares: 15000,
      value: 750000,
      currency: 'PLN',
      transactionCount: 2,
      roles: ['Prezes Zarządu'],
    },
  ],
}

describe('InsiderActivityCard', () => {
  it('renders summary tiles and transaction table rows', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={SAMPLE_DATA}
        loading={false}
        includeAll={false}
        onToggleIncludeAll={() => {}}
      />,
    )

    expect(screen.getByTestId('insider-activity-card')).toBeInTheDocument()
    expect(screen.getByText('Prezes Zarządu')).toBeInTheDocument()
    expect(screen.getByText('Członek Rady Nadzorczej')).toBeInTheDocument()
    expect(screen.getByText('2026-04-02')).toBeInTheDocument()
    expect(screen.getByText('2026-04-06')).toBeInTheDocument()
  })

  it('calls onToggleIncludeAll when the checkbox is clicked', async () => {
    const onToggle = vi.fn()
    renderWithProviders(
      <InsiderActivityCard
        data={SAMPLE_DATA}
        loading={false}
        includeAll={false}
        onToggleIncludeAll={onToggle}
      />,
    )

    const checkbox = screen.getByRole('checkbox')
    await userEvent.click(checkbox)
    expect(onToggle).toHaveBeenCalledWith(true)
  })

  it('renders empty state when there are no reported trades', () => {
    const emptyData: ApiInsiderTransactionsResponse = {
      ...SAMPLE_DATA,
      summary: {
        totalPurchasesCount: 0,
        totalSalesCount: 0,
        totalPurchasesShares: 0,
        totalSalesShares: 0,
        totalPurchasesValue: 0,
        totalSalesValue: 0,
        netShares: 0,
        netValue: 0,
        currency: 'PLN',
      },
      transactions: [],
      chartMarkers: [],
    }

    renderWithProviders(
      <InsiderActivityCard
        data={emptyData}
        loading={false}
        includeAll={false}
        onToggleIncludeAll={() => {}}
      />,
    )

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
