import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { importXtbWallets, previewXtbWallets, type XtbWalletPreview, type XtbWalletsPreview } from '../api/portfoliosApi'
import { XtbWalletImport } from './XtbWalletImport'

vi.mock('../api/portfoliosApi', () => ({ previewXtbWallets: vi.fn(), importXtbWallets: vi.fn() }))
const file = () => new File(['report'], 'IKE.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
const wallet = (name: string): XtbWalletPreview => ({
  id: name, name, sheet: name, version: null, ready: 1, duplicates: 0, errors: 0,
  sourceBrokerAccountId: '00123456', brokerAccountId: name === 'Cash Operations' ? '00123456' : null,
  linksBrokerAccount: name === 'Cash Operations',
  ignored: 0, warnings: [], ledgerError: null, error: null,
  rows: [{ sheet: name, row: 6, symbol: 'KGH.PL', status: 'ready', transaction: {
    id: `trade-${name}`, ticker: 'kgh', side: 'buy', date: '2026-01-02', quantity: '10', price: '100.25', fees: '0', currency: 'PLN',
  } }],
})
const ready = (): XtbWalletsPreview => ({
  ready: 3, errors: 0, newWallets: 3, previewToken: 'reviewed-plan', blockingError: null,
  wallets: [wallet('Closed Positions'), wallet('Cash Operations'), wallet('Open Positions')],
})
let refreshed: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.resetAllMocks()
  refreshed = vi.fn().mockResolvedValue(undefined)
  vi.mocked(previewXtbWallets).mockResolvedValue(ready())
  vi.mocked(importXtbWallets).mockResolvedValue({ wallets: [], imported: 3, duplicates: 0, skipped: 0, created: 3 })
})

async function loadPreview() {
  const user = userEvent.setup()
  await user.upload(screen.getByLabelText('XTB report file'), file())
  await user.click(screen.getByRole('button', { name: 'Preview import' }))
  await screen.findByText('New wallets: 3 · New trades: 3 · Rows needing attention: 0')
  return user
}

describe('XTB worksheet wallets', () => {
  it('previews each worksheet for the account and submits the reviewed plan', async () => {
    const busyChanged = vi.fn()
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} onBusyChange={busyChanged} />)
    const user = await loadPreview()
    expect(importXtbWallets).not.toHaveBeenCalled()
    expect(screen.getByText(/^Closed Positions —/)).toBeVisible()
    expect(screen.getByText(/^Cash Operations —/)).toBeVisible()
    expect(screen.getByText(/^Open Positions —/)).toBeVisible()
    expect(screen.getByText('XTB account 00123456')).toBeVisible()
    expect(screen.getAllByText('Report account 00123456')).toHaveLength(2)
    await user.click(screen.getByText(/^Cash Operations —/))
    expect(screen.getByText('Cash Operations · 6')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Import wallets (3)' }))
    await screen.findByText('Import complete. Wallets created: 3, trades added: 3, duplicates: 0, skipped: 0.')
    expect(previewXtbWallets).toHaveBeenCalledWith(expect.any(File), 17, expect.any(AbortSignal), undefined)
    expect(importXtbWallets).toHaveBeenCalledWith(expect.any(File), 17, 'reviewed-plan', false, expect.any(AbortSignal), undefined)
    expect(refreshed).toHaveBeenCalledTimes(1)
    expect(busyChanged.mock.calls.map(([value]) => value)).toEqual([true, false, true, false])
  })

  it('requires an explicit choice before skipping unsupported rows', async () => {
    const preview = ready()
    preview.errors = 1
    preview.wallets[2].errors = 1
    preview.wallets[2].rows.push({ sheet: 'Open Positions', row: 10, symbol: 'UNSUPPORTED.PL', status: 'error', code: 'unknown_ticker' })
    vi.mocked(previewXtbWallets).mockResolvedValue(preview)
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    const confirm = await screen.findByRole('button', { name: 'Import wallets (3)' })
    expect(confirm).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    await user.click(confirm)
    await waitFor(() => expect(importXtbWallets).toHaveBeenCalledWith(expect.any(File), 17, 'reviewed-plan', true, expect.any(AbortSignal), undefined))
  })

  it.each(['error', 'ledgerError'] as const)('blocks the batch when a worksheet has %s', async code => {
    const preview = ready()
    preview.errors = 1
    preview.wallets[0][code] = code === 'error' ? 'import_unrecognized_format' : 'insufficient_shares'
    vi.mocked(previewXtbWallets).mockResolvedValue(preview)
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    await screen.findByRole('alert')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import wallets (3)' })).toBeDisabled()
    expect(importXtbWallets).not.toHaveBeenCalled()
  })

  it('keeps the reviewed plan for an uncertain save retry and clears it when the file changes', async () => {
    vi.mocked(importXtbWallets).mockRejectedValueOnce(new ApiError(0, 'Offline'))
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = await loadPreview()
    await user.click(screen.getByRole('button', { name: 'Import wallets (3)' }))
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: 'Import wallets (3)' }))
    await screen.findByText(/Import complete\. Wallets created: 3/)
    expect(vi.mocked(importXtbWallets).mock.calls[0].slice(0, 4)).toEqual(vi.mocked(importXtbWallets).mock.calls[1].slice(0, 4))
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    await screen.findByRole('button', { name: 'Import wallets (3)' })
    await user.upload(screen.getByLabelText('XTB report file'), new File(['other'], 'Other.xlsx'))
    expect(screen.queryByRole('button', { name: 'Import wallets (3)' })).not.toBeInTheDocument()
  })

  it.each(['import_preview_changed', 'account_changed'])('discards the approval after %s', async code => {
    vi.mocked(importXtbWallets).mockRejectedValueOnce(new ApiError(409, 'Changed', code))
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = await loadPreview()
    await user.click(screen.getByRole('button', { name: 'Import wallets (3)' }))
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: 'Import wallets (3)' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview import' })).toBeEnabled()
    expect(refreshed).not.toHaveBeenCalled()
  })

  it('lets a recognized empty worksheet create a wallet', async () => {
    const empty = { ...wallet('Closed Positions'), ready: 0, rows: [] }
    vi.mocked(previewXtbWallets).mockResolvedValue({ ...ready(), newWallets: 1, ready: 0, wallets: [empty] })
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    const confirm = await screen.findByRole('button', { name: 'Import wallets (1)' })
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    expect(importXtbWallets).toHaveBeenCalledWith(expect.any(File), 17, 'reviewed-plan', false, expect.any(AbortSignal), undefined)
  })

  it('explains a duplicate report without offering to recreate its wallets', async () => {
    const preview = ready()
    vi.mocked(previewXtbWallets).mockResolvedValue({
      ...preview, newWallets: 0, ready: 0,
      wallets: preview.wallets.map(wallet => ({ ...wallet, version: 1, ready: 0, duplicates: 1, linksBrokerAccount: false })),
    })
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    await screen.findByText('This report has already been imported.')
    expect(screen.queryByRole('button', { name: /^Import wallets/ })).not.toBeInTheDocument()
    expect(importXtbWallets).not.toHaveBeenCalled()
  })

  it('updates the matched wallet and reports the new trades without creating another wallet', async () => {
    const matched = { ...wallet('Cash Operations'), name: 'Retirement', version: 3,
      linksBrokerAccount: false, brokerAccountCurrency: 'EUR' }
    vi.mocked(previewXtbWallets).mockResolvedValue({ ...ready(), newWallets: 0, ready: 1,
      wallets: [matched], skippedSheets: ['Open Positions', 'Closed Positions'] })
    vi.mocked(importXtbWallets).mockResolvedValue({ wallets: [], imported: 1, duplicates: 0, skipped: 0, created: 0 })
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    expect(await screen.findByText(/^Retirement —/)).toBeVisible()
    expect(screen.getByText('Existing wallet')).toBeVisible()
    expect(screen.getByText('Account currency EUR')).toBeVisible()
    expect(screen.getByText('Skipped Open Positions, Closed Positions to avoid overlapping trades.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Import trades (1)' }))
    expect(await screen.findByText('Import complete. Wallets created: 0, trades added: 1, duplicates: 0, skipped: 0.')).toBeVisible()
    expect(refreshed).toHaveBeenCalledOnce()
  })

  it('requires a fresh preview for a manually selected wallet and saves its account currency', async () => {
    const portfolios = [{ id: 'retirement', name: 'Retirement', broker: 'XTB', brokerAccountId: null }]
    render(<XtbWalletImport owner={17} portfolios={portfolios} disabled={false} onImported={refreshed} />)
    const user = await loadPreview()
    await user.selectOptions(screen.getByLabelText('Destination wallet'), 'retirement')
    expect(screen.queryByRole('button', { name: 'Import wallets (3)' })).not.toBeInTheDocument()
    const match = { ...wallet('Cash Operations'), id: 'retirement', name: 'Retirement', version: 2,
      ready: 0, duplicates: 1, brokerAccountCurrency: 'USD', setsBrokerAccountCurrency: true, linksBrokerAccount: false }
    vi.mocked(previewXtbWallets).mockResolvedValue({ ...ready(), newWallets: 0, ready: 0,
      wallets: [match], previewToken: 'manual-target-plan' })
    vi.mocked(importXtbWallets).mockResolvedValue({ wallets: [], imported: 0, duplicates: 1, skipped: 0, created: 0 })
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    await user.click(await screen.findByRole('button', { name: 'Save wallet details' }))
    expect(await screen.findByText('Wallet details saved.')).toBeVisible()
    expect(previewXtbWallets).toHaveBeenLastCalledWith(expect.any(File), 17, expect.any(AbortSignal), 'retirement')
    expect(importXtbWallets).toHaveBeenCalledWith(expect.any(File), 17, 'manual-target-plan', false, expect.any(AbortSignal), 'retirement')
  })

  it('explains when a position-only report has no trades eligible for the matched wallet', async () => {
    vi.mocked(previewXtbWallets).mockResolvedValue({ ...ready(), newWallets: 0, ready: 0,
      wallets: [], skippedSheets: ['Open Positions'] })
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    expect(await screen.findByText('No new trades to import.')).toBeVisible()
    expect(screen.getByText('Skipped Open Positions to avoid overlapping trades.')).toBeVisible()
    expect(screen.queryByText('This report has already been imported.')).not.toBeInTheDocument()
  })

  it('requires a new destination when a manually selected wallet is removed', async () => {
    const portfolios = [{ id: 'retirement', name: 'Retirement', broker: 'XTB', brokerAccountId: null }]
    const match = { ...wallet('Cash Operations'), id: 'retirement', name: 'Retirement', version: 2,
      linksBrokerAccount: false }
    vi.mocked(previewXtbWallets).mockResolvedValue({ ...ready(), newWallets: 0, ready: 1, wallets: [match] })
    const view = render(<XtbWalletImport owner={17} portfolios={portfolios} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('Destination wallet'), 'retirement')
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    await screen.findByRole('button', { name: 'Import trades (1)' })
    view.rerender(<XtbWalletImport owner={17} portfolios={[]} disabled={false} onImported={refreshed} />)
    expect(screen.getByRole('alert')).toHaveTextContent('The selected wallet is no longer available.')
    expect(screen.queryByRole('button', { name: 'Import trades (1)' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview import' })).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('Destination wallet'), '')
    expect(screen.getByRole('button', { name: 'Preview import' })).toBeEnabled()
    expect(importXtbWallets).not.toHaveBeenCalled()
  })

  it('lets an existing worksheet wallet link its account without creating another wallet', async () => {
    const preview = ready()
    vi.mocked(previewXtbWallets).mockResolvedValue({
      ...preview, newWallets: 0, ready: 0,
      wallets: preview.wallets.map(wallet => ({ ...wallet, version: 1, ready: 0, duplicates: 1 })),
    })
    vi.mocked(importXtbWallets).mockResolvedValue({ wallets: [], imported: 0, duplicates: 3, skipped: 0, created: 0 })
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const user = userEvent.setup()
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview import' }))
    await user.click(await screen.findByRole('button', { name: 'Link XTB accounts' }))
    expect(await screen.findByText('XTB accounts linked to the saved wallets.')).toBeVisible()
    expect(importXtbWallets).toHaveBeenCalledWith(expect.any(File), 17, 'reviewed-plan', false, expect.any(AbortSignal), undefined)
  })

  it('shows a batch limit error before save and leaves confirmation disabled', async () => {
    vi.mocked(previewXtbWallets).mockResolvedValue({ ...ready(), blockingError: 'portfolio_limit' })
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    await loadPreview()
    expect(screen.getByRole('alert')).toHaveTextContent('You can have up to 20 portfolios.')
    expect(screen.getByRole('button', { name: 'Import wallets (3)' })).toBeDisabled()
  })

  it('cancels a pending request when the account view closes', async () => {
    let resolve!: (value: XtbWalletsPreview) => void
    vi.mocked(previewXtbWallets).mockImplementation(() => new Promise(done => { resolve = done }))
    const view = render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    fireEvent.change(screen.getByLabelText('XTB report file'), { target: { files: [file()] } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview import' }))
    const signal = vi.mocked(previewXtbWallets).mock.calls[0][2]
    view.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => resolve(ready()))
    expect(importXtbWallets).not.toHaveBeenCalled()
    expect(refreshed).not.toHaveBeenCalled()
  })

  it('rejects oversized files before sending them', async () => {
    render(<XtbWalletImport owner={17} disabled={false} onImported={refreshed} />)
    const big = new File(['x'], 'TooLarge.xlsx')
    Object.defineProperty(big, 'size', { value: 5 * 1024 * 1024 + 1 })
    fireEvent.change(screen.getByLabelText('XTB report file'), { target: { files: [big] } })
    expect(screen.getByRole('alert')).toHaveTextContent('The file is too large.')
    expect(screen.getByRole('button', { name: 'Preview import' })).toBeDisabled()
    expect(previewXtbWallets).not.toHaveBeenCalled()
  })
})
