import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { useLocation, useNavigate } from 'react-router-dom'
import { renderWithProviders, screen } from '../test/utils'
import { booleanParam, enumParam, numberParam, textParam, useUrlState } from './useUrlState'
import { useTableSort } from './useTableSort'
import { sortParam } from '../lib/urlSort'

const schema = {
  q: textParam(), favorites: booleanParam(), minPrice: numberParam(null),
  signal: enumParam('all', ['all', 'Buy']),
  sort: sortParam({ key: 'change', dir: 'desc' }, ['change', 'ticker']),
}

function Controls() {
  const url = useUrlState(schema)
  const [query, setQuery] = url.field('q')
  const [favorites, setFavorites] = url.field('favorites')
  const { onSort } = useTableSort({ key: 'change', dir: 'desc' }, () => 'asc', undefined, url.field('sort'))
  const location = useLocation()
  const navigate = useNavigate()
  return <>
    <input aria-label="Search" value={query} onChange={(event) => setQuery(event.target.value)} />
    <button aria-pressed={favorites} onClick={() => setFavorites((previous) => !previous)}>Favorites</button>
    <button onClick={() => onSort('ticker', true)}>Then ticker</button>
    <button onClick={() => { setQuery(''); setFavorites(false) }}>Clear</button>
    <button onClick={() => navigate(-1)}>Back</button>
    <button onClick={() => navigate(1)}>Forward</button>
    <output aria-label="State">{JSON.stringify(url.state)}</output>
    <output aria-label="URL">{location.pathname}{location.search}{location.hash}</output>
  </>
}

function state() { return JSON.parse(screen.getByLabelText('State').textContent!) }
function currentUrl() { return new URL(screen.getByLabelText('URL').textContent!, 'https://example.test') }

describe('URL list state', () => {
  it('restores combined choices immediately from a link', () => {
    renderWithProviders(<Controls />, { initialEntries: ['/list?q=KGH&favorites=1&minPrice=12.5&signal=Buy&sortBy=ticker,change&sortDir=asc,desc'] })
    expect(state()).toEqual({ q: 'KGH', favorites: true, minPrice: 12.5, signal: 'Buy',
      sort: [{ key: 'ticker', dir: 'asc' }, { key: 'change', dir: 'desc' }] })
  })

  it('updates the URL, preserves other parameters and hash, and supports history', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Controls />, { initialEntries: ['/list?source=shared#ranking'] })
    await user.click(screen.getByText('Favorites'))
    expect(currentUrl().searchParams.get('favorites')).toBe('1')
    await user.click(screen.getByText('Then ticker'))
    expect(currentUrl().searchParams.get('sortBy')).toBe('change,ticker')
    expect(currentUrl().searchParams.get('sortDir')).toBe('desc,asc')
    expect(currentUrl().searchParams.get('source')).toBe('shared')
    expect(currentUrl().hash).toBe('#ranking')
    await user.click(screen.getByText('Back'))
    expect(state().favorites).toBe(true)
    expect(state().sort).toEqual([{ key: 'change', dir: 'desc' }])
    await user.click(screen.getByText('Back'))
    expect(state().favorites).toBe(false)
    await user.click(screen.getByText('Forward'))
    expect(state().favorites).toBe(true)
  })

  it('composes multiple setters when clearing filters and survives a remount', async () => {
    const user = userEvent.setup()
    const view = renderWithProviders(<Controls />, { initialEntries: ['/list?q=KGH&favorites=1&sortBy=ticker&sortDir=asc'] })
    await user.click(screen.getByText('Clear'))
    expect(currentUrl().searchParams.has('q')).toBe(false)
    expect(currentUrl().searchParams.has('favorites')).toBe(false)
    expect(state().sort).toEqual([{ key: 'ticker', dir: 'asc' }])
    const link = currentUrl().pathname + currentUrl().search
    view.unmount()
    renderWithProviders(<Controls />, { initialEntries: [link] })
    expect(state().q).toBe('')
    expect(state().favorites).toBe(false)
    expect(state().sort).toEqual([{ key: 'ticker', dir: 'asc' }])
  })

  it('rejects invalid values and duplicate, unknown or excessive sort levels', () => {
    renderWithProviders(<Controls />, { initialEntries: ['/list?favorites=oops&minPrice=-1&signal=oops&sortBy=unknown,ticker,ticker,change&sortDir=desc,asc,desc,asc'] })
    expect(state()).toMatchObject({ favorites: false, minPrice: null, signal: 'all',
      sort: [{ key: 'ticker', dir: 'asc' }, { key: 'change', dir: 'asc' }] })
  })

  it('falls back for malformed sort directions and non-finite numbers', () => {
    renderWithProviders(<Controls />, { initialEntries: ['/list?minPrice=Infinity&sortBy=ticker&sortDir=up'] })
    expect(state().minPrice).toBeNull()
    expect(state().sort).toEqual([{ key: 'change', dir: 'desc' }])
  })
})
