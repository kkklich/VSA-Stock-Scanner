import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { watchlistsRequest, type Watchlist } from '../api/watchlistsApi'
import { useWatchlists } from '../hooks/useWatchlists'
import { FAVORITES_KEY } from '../lib/favorites'
import { WatchlistsProvider } from './WatchlistsProvider'
import { WatchlistControls } from './WatchlistControls'

const auth = vi.hoisted(() => ({ user: { id: 1 } as { id: number } | null, loading: false, config: { enabled: true } }))
vi.mock('../hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('../api/watchlistsApi', () => ({ watchlistsRequest: vi.fn() }))

function Probe() {
  const { stars, toggleStar, busy } = useWatchlists()
  return <>
    <output aria-label="Stars">{Object.keys(stars).filter((key) => stars[key]).join(',')}</output>
    <button disabled={busy} onClick={() => toggleStar('PKN')}>Toggle PKN</button>
    <WatchlistControls />
  </>
}

function App() {
  return <MemoryRouter><WatchlistsProvider><Probe /></WatchlistsProvider></MemoryRouter>
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  auth.user = { id: 1 }
  auth.loading = false
})

describe('account watchlists', () => {
  it('creates, selects, renames, imports and deletes a list without replacing guest favorites', async () => {
    const user = userEvent.setup()
    localStorage.setItem(FAVORITES_KEY, JSON.stringify({ AAPL: true }))
    let lists: Watchlist[] = [{ id: 'first', name: 'Favorites', tickers: [] }]
    vi.mocked(watchlistsRequest).mockImplementation(async (method, path, body) => {
      const payload = body as { name?: string; tickers?: string[] }
      if (method === 'POST' && path === '') lists.push({ id: 'second', name: payload.name!, tickers: [] })
      if (method === 'PATCH') lists = lists.map((list) => list.id === path?.slice(1) ? { ...list, name: payload.name! } : list)
      if (method === 'PUT') lists = lists.map((list) => path === `/${list.id}/members` ? { ...list, tickers: [...new Set([...list.tickers, ...payload.tickers!])] } : list)
      if (method === 'DELETE') lists = lists.filter((list) => path !== `/${list.id}`)
      return structuredClone(lists)
    })
    render(<App />)
    await screen.findByRole('option', { name: 'Favorites (0)' })
    await user.click(screen.getByRole('button', { name: 'New list' }))
    await user.type(screen.getByRole('textbox', { name: 'List name' }), 'Long term')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('second'))
    await user.click(screen.getByRole('button', { name: 'Toggle PKN' }))
    await waitFor(() => expect(screen.getByLabelText('Stars')).toHaveTextContent('PKN'))
    await user.click(screen.getByRole('button', { name: 'Copy browser favorites' }))
    await waitFor(() => expect(screen.getByLabelText('Stars')).toHaveTextContent('AAPL'))
    expect(JSON.parse(localStorage.getItem(FAVORITES_KEY)!)).toEqual({ AAPL: true })
    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.clear(screen.getByRole('textbox', { name: 'List name' }))
    await user.type(screen.getByRole('textbox', { name: 'List name' }), 'Research')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByRole('option', { name: 'Research (2)' })
    await user.click(screen.getByRole('button', { name: 'Delete list' }))
    await user.click(screen.getAllByRole('button', { name: 'Delete list' })[1])
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('first'))
    expect(screen.getByLabelText('Stars')).toBeEmptyDOMElement()
  })

  it('keeps confirmed stars on a failed write and can retry loading', async () => {
    vi.mocked(watchlistsRequest).mockResolvedValue([{ id: 'one', name: 'Favorites', tickers: [] }])
    render(<App />)
    await screen.findByRole('option', { name: 'Favorites (0)' })
    vi.mocked(watchlistsRequest).mockRejectedValueOnce(new ApiError(500, 'error'))
    fireEvent.click(screen.getByRole('button', { name: 'Toggle PKN' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Stars')).toBeEmptyDOMElement()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('discards an old account response after switching accounts', async () => {
    let complete!: (lists: Watchlist[]) => void
    vi.mocked(watchlistsRequest).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve }))
    const view = render(<App />)
    auth.user = { id: 2 }
    vi.mocked(watchlistsRequest).mockResolvedValue([{ id: 'two', name: 'Private B', tickers: ['MSFT'] }])
    view.rerender(<App />)
    await screen.findByRole('option', { name: 'Private B (1)' })
    await act(async () => { complete([{ id: 'one', name: 'Private A', tickers: ['PKN'] }]) })
    expect(screen.getByLabelText('Stars')).toHaveTextContent('MSFT')
    expect(screen.queryByText('Private A (1)')).not.toBeInTheDocument()
    auth.user = null
    view.rerender(<App />)
    expect(screen.getByLabelText('Stars')).toBeEmptyDOMElement()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('refreshes changes from another device on focus', async () => {
    vi.mocked(watchlistsRequest).mockResolvedValue([{ id: 'one', name: 'Favorites', tickers: [] }])
    render(<App />)
    await screen.findByRole('option', { name: 'Favorites (0)' })
    vi.mocked(watchlistsRequest).mockResolvedValue([{ id: 'one', name: 'Favorites', tickers: ['PKN'] }])
    fireEvent(window, new Event('focus'))
    await waitFor(() => expect(screen.getByLabelText('Stars')).toHaveTextContent('PKN'))
  })

  it('preserves guest mode without contacting the account API', async () => {
    auth.user = null
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Toggle PKN' }))
    expect(screen.getByLabelText('Stars')).toHaveTextContent('PKN')
    expect(JSON.parse(localStorage.getItem(FAVORITES_KEY)!)).toEqual({ PKN: true })
    expect(watchlistsRequest).not.toHaveBeenCalled()
  })

  it('remembers selection per account and aborts requests when leaving it', async () => {
    localStorage.setItem('stockpilot:active-watchlist:1', 'second')
    vi.mocked(watchlistsRequest).mockResolvedValue([
      { id: 'first', name: 'Favorites', tickers: [] },
      { id: 'second', name: 'Research', tickers: ['PKN'] },
    ])
    const view = render(<App />)
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('second'))
    expect(screen.getByLabelText('Stars')).toHaveTextContent('PKN')
    const signal = vi.mocked(watchlistsRequest).mock.calls[0][3]
    auth.user = null
    view.rerender(<App />)
    expect(signal?.aborted).toBe(true)
    expect(screen.getByLabelText('Stars')).toBeEmptyDOMElement()
  })
})
