import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from '../api/client'
import { AddStockSection } from './AddStockSection'

const auth = vi.hoisted(() => ({ user: { id: 1 } as { id: number } | null }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../hooks/useMarkets', () => ({ useMarkets: () => [{ id: 'gpw', name: 'GPW' }] }))
vi.mock('../api/client', async importOriginal => {
  const original = await importOriginal<typeof import('../api/client')>()
  return { ...original, apiFetch: vi.fn() }
})

beforeEach(() => {
  auth.user = { id: 1 }
  vi.mocked(apiFetch).mockReset()
})

function renderForm() {
  render(<MemoryRouter><AddStockSection /></MemoryRouter>)
}

function submitStock() {
  fireEvent.change(screen.getByLabelText('Stock ticker'), { target: { value: ' NEW ' } })
  fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'New Company' } })
  fireEvent.change(screen.getByLabelText('Company country'), { target: { value: 'Poland' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add stock' }))
}

it('asks guests to sign in and hides the form', () => {
  auth.user = null
  renderForm()
  expect(screen.getByRole('link', { name: 'Sign in to add a stock' })).toHaveAttribute('href', '/login')
  expect(screen.queryByLabelText('Stock ticker')).not.toBeInTheDocument()
  expect(apiFetch).not.toHaveBeenCalled()
})

it('saves entered details under the current account and links to the stock', async () => {
  vi.mocked(apiFetch).mockResolvedValue({ ticker: 'new', name: 'New Company' })
  renderForm()
  submitStock()
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Stock added:'))
  expect(apiFetch).toHaveBeenCalledWith('/api/custom-stocks', {
    method: 'POST', headers: { 'X-Expected-User-Id': '1' },
    body: JSON.stringify({ ticker: 'NEW', name: 'New Company', country: 'Poland', market: 'gpw' }),
  })
  expect(screen.getByRole('link', { name: 'New Company (NEW)' })).toHaveAttribute('href', '/stock/new')
})

it('shows duplicate errors and preserves the form for correction', async () => {
  vi.mocked(apiFetch).mockRejectedValue(new ApiError(409, 'stock_exists', 'stock_exists'))
  renderForm()
  submitStock()
  expect(await screen.findByRole('alert')).toHaveTextContent('This stock is already tracked.')
  expect(screen.getByLabelText('Company name')).toHaveValue('New Company')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
