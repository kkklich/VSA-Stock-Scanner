import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { importXtb, previewXtb, type Portfolio, type XtbPreview } from '../api/portfoliosApi'
import { XtbImport } from './XtbImport'

vi.mock('../api/portfoliosApi', () => ({ previewXtb: vi.fn(), importXtb: vi.fn() }))
const portfolio: Portfolio = { id: 'one', name: 'Retirement', broker: 'XTB', costMethod: 'fifo',
  version: 1, createdAt: '2026-01-01', positions: [], totals: [], transactions: [] }
const file = () => new File(['report'], 'history.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
const ready = (): XtbPreview => ({
  version: 1, ready: 1, duplicates: 1, errors: 0, ignored: 2, warnings: ['fees_missing'], ledgerError: null,
  rows: [{ sheet: 'Cash Operations', row: 6, symbol: 'KGH.PL', status: 'ready', transaction: {
    id: 'trade-1', ticker: 'kgh', side: 'buy', date: '2026-01-02', quantity: '10', price: '100.25', fees: '0', currency: 'PLN', executedAt: '2026-01-02T12:00:00.000000',
  } }],
})
let refreshed: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.resetAllMocks()
  refreshed = vi.fn().mockResolvedValue(undefined)
  vi.mocked(previewXtb).mockResolvedValue(ready())
  vi.mocked(importXtb).mockResolvedValue({ imported: 1, duplicates: 1, skipped: 0, version: 2 })
})

async function loadPreview() {
  const user = userEvent.setup()
  await user.upload(screen.getByLabelText('XTB report file'), file())
  await user.click(screen.getByRole('button', { name: 'Preview file' }))
  await screen.findByText('New trades: 1 · Already saved: 1 · Rows needing attention: 0')
  return user
}

describe('XTB portfolio import', () => {
  it('previews without saving and only sends the original file after confirmation', async () => {
    render(<XtbImport portfolio={portfolio} disabled={false} onImported={refreshed} />)
    const user = await loadPreview()
    expect(importXtb).not.toHaveBeenCalled()
    expect(screen.getByText('KGH')).toBeVisible()
    expect(screen.getByText(/Some trades have no commission/)).toBeVisible()
    expect(screen.getByText('Cash operations and summary rows omitted: 2.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Import 1 trades into “Retirement”' }))
    await screen.findByText('Import complete. Added: 1, duplicates: 1, skipped: 0.')
    expect(importXtb).toHaveBeenCalledWith('one', expect.any(File), 1, false, expect.any(AbortSignal))
    expect(refreshed).toHaveBeenCalledTimes(1)
  })

  it('requires an explicit choice before skipping invalid rows', async () => {
    vi.mocked(previewXtb).mockResolvedValue({ ...ready(), errors: 1 })
    const user = userEvent.setup()
    render(<XtbImport portfolio={portfolio} disabled={false} onImported={refreshed} />)
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview file' }))
    const confirm = await screen.findByRole('button', { name: 'Import 1 trades into “Retirement”' })
    expect(confirm).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    await waitFor(() => expect(importXtb).toHaveBeenCalledWith('one', expect.any(File), 1, true, expect.any(AbortSignal)))
  })

  it('blocks an invalid ledger even when partial import is selected', async () => {
    vi.mocked(previewXtb).mockResolvedValue({ ...ready(), errors: 1, ledgerError: 'insufficient_shares' })
    const user = userEvent.setup()
    render(<XtbImport portfolio={portfolio} disabled={false} onImported={refreshed} />)
    await user.upload(screen.getByLabelText('XTB report file'), file())
    await user.click(screen.getByRole('button', { name: 'Preview file' }))
    await screen.findByRole('alert')
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Import 1 trades into “Retirement”' })).toBeDisabled()
  })

  it('requires a new preview after the portfolio changes or the file is replaced', async () => {
    const view = render(<XtbImport portfolio={portfolio} disabled={false} onImported={refreshed} />)
    const user = await loadPreview()
    view.rerender(<XtbImport portfolio={{ ...portfolio, version: 2 }} disabled={false} onImported={refreshed} />)
    expect(screen.getByRole('button', { name: 'Import 1 trades into “Retirement”' })).toBeDisabled()
    await user.upload(screen.getByLabelText('XTB report file'), new File(['other'], 'other.csv', { type: 'text/csv' }))
    expect(screen.queryByRole('button', { name: 'Import 1 trades into “Retirement”' })).not.toBeInTheDocument()
  })

  it('retains the original preview on an uncertain save so the same import can be retried', async () => {
    vi.mocked(importXtb).mockRejectedValueOnce(new ApiError(0, 'Offline'))
    render(<XtbImport portfolio={portfolio} disabled={false} onImported={refreshed} />)
    const user = await loadPreview()
    await user.click(screen.getByRole('button', { name: 'Import 1 trades into “Retirement”' }))
    await screen.findByRole('alert')
    expect(refreshed).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Import 1 trades into “Retirement”' }))
    await screen.findByText('Import complete. Added: 1, duplicates: 1, skipped: 0.')
    expect(vi.mocked(importXtb).mock.calls[0].slice(0, 4)).toEqual(vi.mocked(importXtb).mock.calls[1].slice(0, 4))
  })

  it('cancels a pending preview when the portfolio view closes', async () => {
    let resolve!: (value: XtbPreview) => void
    vi.mocked(previewXtb).mockImplementation(() => new Promise(done => { resolve = done }))
    const view = render(<XtbImport portfolio={portfolio} disabled={false} onImported={refreshed} />)
    fireEvent.change(screen.getByLabelText('XTB report file'), { target: { files: [file()] } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview file' }))
    const signal = vi.mocked(previewXtb).mock.calls[0][2]
    view.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => resolve(ready()))
    expect(importXtb).not.toHaveBeenCalled()
  })
})
