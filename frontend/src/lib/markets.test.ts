// The frontend half of the market registry: ticker display, the stored market
// choice, and which market a screen may actually request.

import { beforeEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import {
  ALL_MARKETS,
  displayTicker,
  effectiveMarket,
  GPW_MARKET,
  MARKET_STORAGE_KEY,
  marketOfTicker,
  plnHint,
  readStoredMarket,
  setMarketSelection,
  toPln,
  useMarketSelection,
} from './markets'

beforeEach(() => {
  localStorage.clear()
})

describe('tickers', () => {
  it('drops the market suffix for display', () => {
    expect(displayTicker('AAPL.US')).toBe('AAPL')
    expect(displayTicker('BT-A.L')).toBe('BT-A')
    expect(displayTicker('KGH')).toBe('KGH')
  })

  it('reads the market from the suffix', () => {
    expect(marketOfTicker('kgh')).toBe('gpw')
    expect(marketOfTicker('AAPL.US')).toBe('us')
    expect(marketOfTicker('sap.de')).toBe('de')
    expect(marketOfTicker('MC.PA')).toBe('fr')
    expect(marketOfTicker('asml.as')).toBe('nl')
    expect(marketOfTicker('hsba.l')).toBe('uk')
    // An unknown suffix is not a market we know of.
    expect(marketOfTicker('x.zz')).toBe('gpw')
  })
})

describe('the stored choice', () => {
  it('defaults to the GPW', () => {
    expect(readStoredMarket()).toBe(GPW_MARKET)
  })

  it('ignores garbage in storage', () => {
    localStorage.setItem(MARKET_STORAGE_KEY, '<script>')
    expect(readStoredMarket()).toBe(GPW_MARKET)
  })

  it('is shared by every component and remembered', () => {
    const first = renderHook(() => useMarketSelection())
    const second = renderHook(() => useMarketSelection())
    act(() => setMarketSelection('us'))
    expect(first.result.current.selection).toBe('us')
    expect(second.result.current.selection).toBe('us')
    expect(localStorage.getItem(MARKET_STORAGE_KEY)).toBe('us')
    act(() => first.result.current.setSelection(ALL_MARKETS))
    expect(second.result.current.selection).toBe(ALL_MARKETS)
  })
})

describe('effectiveMarket', () => {
  const served = ['gpw', 'us', 'uk']

  it('never waits for the GPW', () => {
    expect(effectiveMarket('gpw', null, { allowAll: true })).toBe('gpw')
  })

  it('waits for the catalogue before trusting another choice', () => {
    expect(effectiveMarket('us', null, { allowAll: true })).toBeNull()
    expect(effectiveMarket('us', served, { allowAll: true })).toBe('us')
  })

  it('falls back to the GPW for a market that is not served', () => {
    expect(effectiveMarket('de', served, { allowAll: true })).toBe('gpw')
  })

  it('keeps "all" only where a screen can combine markets', () => {
    expect(effectiveMarket(ALL_MARKETS, served, { allowAll: true })).toBe(ALL_MARKETS)
    expect(effectiveMarket(ALL_MARKETS, served, { allowAll: false })).toBe('gpw')
  })

  it('treats "all" on a GPW-only site as the GPW', () => {
    expect(effectiveMarket(ALL_MARKETS, ['gpw'], { allowAll: true })).toBe('gpw')
  })
})

describe('money across markets', () => {
  it('converts a quote to approximate złoty', () => {
    expect(toPln(100, 'PLN')).toBe(100)
    expect(toPln(100, 'USD')).toBeCloseTo(380)
    expect(toPln(100, 'EUR')).toBeCloseTo(435)
    // London quotes most lines in PENCE, which is the whole point: 17,760
    // there is ~906 PLN, far less than 6,242 dollars (~23,720 PLN), however
    // much bigger the raw figure looks.
    expect(toPln(17_760, 'GBp')).toBeCloseTo(905.76)
    expect(toPln(6_242.23, 'USD')).toBeCloseTo(23_720.47)
    // Yahoo's other spelling of the same unit.
    expect(toPln(1000, 'GBX')).toBe(toPln(1000, 'GBp'))
  })

  it('reads a missing currency as złoty, like the API model does', () => {
    expect(toPln(100, undefined)).toBe(100)
    expect(toPln(100, null)).toBe(100)
  })

  it('has no answer for a currency it has no rate for', () => {
    expect(toPln(100, 'JPY')).toBeNull()
    expect(toPln(null, 'USD')).toBeNull()
  })

  it('offers a hint only where there is something to explain', () => {
    // A złoty price converts to itself — a second line would be noise.
    expect(plnHint(100, 'PLN')).toBeNull()
    expect(plnHint(100, undefined)).toBeNull()
    expect(plnHint(100, 'USD')).toBeCloseTo(380)
  })
})
