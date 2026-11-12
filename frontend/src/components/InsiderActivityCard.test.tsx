import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen, within } from '../test/utils'
import { InsiderActivityCard } from './InsiderActivityCard'
import type { ApiInsiderTransactionsResponse } from '../api/stocksApi'
import i18n from '../i18n'

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
    expect(screen.getByText('2026-04-01')).toBeInTheDocument()
    expect(screen.getByText('2026-04-05')).toBeInTheDocument()
    expect(screen.getByText('Jan Kowalski')).toBeInTheDocument()
  })

  it('does not substitute the publication date for an unknown trade date', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={{ ...SAMPLE_DATA, transactions: [{ ...SAMPLE_DATA.transactions[0], tradeDate: null }] }}
        loading={false}
        includeAll={false}
        onToggleIncludeAll={() => {}}
      />,
    )
    const cells = screen.getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('—')
    expect(cells[1]).toHaveTextContent('2026-04-02')
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

  it('shows each person and currency with bought, sold and net shares', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={{
          ...SAMPLE_DATA,
          byInsider: [
            {
              insiderName: 'Jan Kowalski', currency: 'PLN',
              totalPurchasesCount: 2, totalSalesCount: 1,
              totalPurchasesShares: 15000, totalSalesShares: 2000,
              totalPurchasesValue: 750000, totalSalesValue: 110000,
              netShares: 13000, netValue: 640000,
            },
            {
              insiderName: 'Jan Kowalski', currency: 'EUR',
              totalPurchasesCount: 1, totalSalesCount: 0,
              totalPurchasesShares: null, totalSalesShares: 0,
              totalPurchasesValue: null, totalSalesValue: 0,
              netShares: null, netValue: null,
            },
          ],
        }}
        loading={false}
        includeAll={false}
        onToggleIncludeAll={() => {}}
      />,
    )

    const table = screen.getByRole('table', { name: i18n.t('insider.byPersonTitle') })
    const rows = within(table).getAllByRole('row')
    expect(within(rows[1]).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'Jan Kowalski', 'PLN', (15000).toLocaleString(), (2000).toLocaleString(), `+${(13000).toLocaleString()}`,
    ])
    expect(within(rows[2]).getAllByRole('cell').map((cell) => cell.textContent)).toEqual([
      'Jan Kowalski', 'EUR', i18n.t('insider.unknown'), '0', i18n.t('insider.unknown'),
    ])
  })

  it('keeps actual zero share counts and prices distinct from missing values', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={{
          ...SAMPLE_DATA,
          transactions: [{ ...SAMPLE_DATA.transactions[0], shares: 0, price: 0, value: null }],
        }}
        loading={false}
        includeAll={true}
        onToggleIncludeAll={() => {}}
      />,
    )
    const table = screen.getByRole('table', { name: i18n.t('insider.title') })
    const cells = within(table).getAllByRole('cell')
    expect(cells[4]).toHaveTextContent(/^0$/)
    expect(cells[5]).not.toHaveTextContent('—')
    expect(cells[5]).toHaveTextContent('0')
    expect(cells[6]).toHaveTextContent('—')
  })

  it('does not label incomplete purchase totals as zero shares or a neutral balance', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={{
          ...SAMPLE_DATA,
          summary: {
            ...SAMPLE_DATA.summary,
            totalPurchasesCount: 1, totalSalesCount: 0,
            totalPurchasesShares: 0, totalSalesShares: 0,
            totalPurchasesValue: 0, totalSalesValue: 0, netShares: 0, netValue: 0,
          },
          transactions: [{ ...SAMPLE_DATA.transactions[0], shares: null, price: null, value: null }],
        }}
        loading={false} includeAll={false} onToggleIncludeAll={() => {}}
      />,
    )
    const purchasesTile = screen.getByText(i18n.t('insider.purchases')).parentElement?.parentElement
    expect(purchasesTile).toHaveTextContent(i18n.t('insider.unknown'))
    expect(purchasesTile).not.toHaveTextContent(`0 ${i18n.t('insider.sharesUnit')}`)
    expect(screen.queryByText(i18n.t('insider.netNeutral'))).not.toBeInTheDocument()
  })

  it('keeps a known zero balance neutral', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={{
          ...SAMPLE_DATA,
          summary: {
            ...SAMPLE_DATA.summary,
            totalPurchasesCount: 1, totalSalesCount: 0,
            totalPurchasesShares: 0, totalSalesShares: 0,
            totalPurchasesValue: 0, totalSalesValue: 0, netShares: 0, netValue: 0,
          },
          transactions: [{ ...SAMPLE_DATA.transactions[0], shares: 0, price: 0, value: 0 }],
        }}
        loading={false} includeAll={false} onToggleIncludeAll={() => {}}
      />,
    )
    expect(screen.getByText(i18n.t('insider.netNeutral'))).toBeInTheDocument()
    expect(screen.queryByText(i18n.t('insider.unknown'))).not.toBeInTheDocument()
  })

  it('allows ESPI refresh and disables refresh during a request', async () => {
    const onRefresh = vi.fn()
    const { rerender } = renderWithProviders(
      <InsiderActivityCard
        data={SAMPLE_DATA} loading={false} includeAll={false}
        onToggleIncludeAll={() => {}} onRefresh={onRefresh}
      />,
    )
    const refresh = screen.getByRole('button', { name: i18n.t('insider.refresh') })
    await userEvent.click(refresh)
    expect(onRefresh).toHaveBeenCalledTimes(1)

    rerender(
      <InsiderActivityCard
        data={SAMPLE_DATA} loading={true} includeAll={false}
        onToggleIncludeAll={() => {}} onRefresh={onRefresh}
      />,
    )
    expect(screen.getByRole('button', { name: i18n.t('insider.refresh') })).toBeDisabled()
  })

  it('shows fetch errors with retry instead of an empty-trades claim', async () => {
    const onRefresh = vi.fn()
    renderWithProviders(
      <InsiderActivityCard
        data={null} loading={false} includeAll={false}
        onToggleIncludeAll={() => {}} onRefresh={onRefresh}
        error="Nie udało się pobrać raportów ESPI."
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się pobrać raportów ESPI.')
    expect(screen.queryByText(i18n.t('insider.empty'))).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: i18n.t('insider.retry') }))
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('shows partial-read warnings and keeps unsafe source URLs out of links', async () => {
    const warning = 'Nie odczytano załącznika: możliwy skan PDF.'
    renderWithProviders(
      <InsiderActivityCard
        data={{
          ...SAMPLE_DATA, warnings: [warning],
          transactions: [{ ...SAMPLE_DATA.transactions[0], sourceUrl: 'javascript:alert(1)' }],
        }}
        loading={false} includeAll={false} onToggleIncludeAll={() => {}}
      />,
    )
    await userEvent.click(screen.getByText(`${i18n.t('insider.warningsTitle')} (1)`))
    expect(screen.getByText(warning)).toBeVisible()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText(i18n.t('insider.gpwSourceNote'))).toBeInTheDocument()
  })

  it('shows share totals instead of adding amounts in different currencies', () => {
    renderWithProviders(
      <InsiderActivityCard
        data={{
          ...SAMPLE_DATA,
          summary: { ...SAMPLE_DATA.summary, netValue: -100, netShares: 13000 },
          transactions: [SAMPLE_DATA.transactions[0], { ...SAMPLE_DATA.transactions[1], currency: 'EUR' }],
        }}
        loading={false} includeAll={false} onToggleIncludeAll={() => {}}
      />,
    )
    expect(screen.getByText(i18n.t('insider.mixedCurrenciesNote'))).toBeInTheDocument()
    expect(screen.getByText(i18n.t('insider.netBuying'))).toBeInTheDocument()
    expect(screen.queryByText(i18n.t('insider.netSelling'))).not.toBeInTheDocument()
    expect(screen.getByText(
      `${(15000).toLocaleString()} ${i18n.t('insider.sharesUnit')}`,
      { normalizer: (text) => text },
    )).toBeInTheDocument()
  })
})
