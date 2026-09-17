// Which stock market the list pages show — the frontend half of the backend's
// market registry (backend-python/app/markets.py).
//
// A GPW ticker is bare ("KGH"); a stock from any other market carries a market
// suffix ("AAPL.US", "SAP.DE", "HSBA.L"). The API always sends the full ticker
// and that is what links, favorites and API calls use; `displayTicker` drops
// the suffix for show, and a small market chip says where the stock trades.
//
// The chosen market is a per-browser preference shared by every page (like the
// theme): `useMarketSelection()`. Which markets exist is the backend's call
// (GET /api/stocks/markets, see `hooks/useMarkets`); a stored choice the
// deployment does not serve falls back to the GPW.

import { useSyncExternalStore } from 'react'

/** The home market — always served, and the default. */
export const GPW_MARKET = 'gpw'
/** Every served market side by side (only where a screen can combine them). */
export const ALL_MARKETS = 'all'

/** A market id ("gpw", "us", …) or ALL_MARKETS. */
export type MarketSelection = string

export const MARKET_STORAGE_KEY = 'stockpilot:market'

/** App ticker suffix → market id (mirrors `ticker_suffix` in app/markets.py). */
const SUFFIX_TO_MARKET: Record<string, string> = {
  us: 'us',
  de: 'de',
  pa: 'fr',
  as: 'nl',
  l: 'uk',
}

/** The short code on a market chip. The GPW, the home market, gets none. */
export const MARKET_CODES: Record<string, string> = {
  gpw: 'PL',
  us: 'US',
  de: 'DE',
  fr: 'FR',
  nl: 'NL',
  uk: 'UK',
}

/** The market a ticker trades on, read from its suffix. */
export function marketOfTicker(ticker: string): string {
  const dot = ticker.lastIndexOf('.')
  if (dot < 0) return GPW_MARKET
  return SUFFIX_TO_MARKET[ticker.slice(dot + 1).toLowerCase()] ?? GPW_MARKET
}

/** The exchange symbol without the app's market suffix ("AAPL.US" → "AAPL"). */
export function displayTicker(ticker: string): string {
  const dot = ticker.lastIndexOf('.')
  return dot < 0 ? ticker : ticker.slice(0, dot)
}

// ── The stored choice ─────────────────────────────────────────────────────────

const VALID_SELECTION = /^[a-z]{2,8}$/

/** The stored choice, or the GPW when nothing valid is stored. */
export function readStoredMarket(): MarketSelection {
  try {
    const raw = localStorage.getItem(MARKET_STORAGE_KEY)
    return raw && VALID_SELECTION.test(raw) ? raw : GPW_MARKET
  } catch {
    // Private mode / storage disabled.
    return GPW_MARKET
  }
}

const listeners = new Set<() => void>()

/** Change the market every list page shows (and remember it). */
export function setMarketSelection(next: MarketSelection): void {
  try {
    localStorage.setItem(MARKET_STORAGE_KEY, next)
  } catch {
    /* ignore quota / private-mode errors */
  }
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The market the user picked, plus a setter. */
export function useMarketSelection() {
  // Read straight from storage: a primitive, so equal reads are stable.
  const selection = useSyncExternalStore(subscribe, readStoredMarket, () => GPW_MARKET)
  return { selection, setSelection: setMarketSelection }
}

/**
 * The market a screen should actually request.
 *
 * `served` is the catalogue from the backend (null while it loads). Returns
 * null only while a non-default choice is waiting for the catalogue, so a
 * screen never asks for a market the deployment has since switched off. A
 * screen that shows one market at a time (`allowAll: false`) turns "all" into
 * the GPW; a deployment that serves only the GPW turns everything into it.
 */
export function effectiveMarket(
  selection: MarketSelection,
  served: string[] | null,
  { allowAll }: { allowAll: boolean },
): MarketSelection | null {
  if (selection === GPW_MARKET) return GPW_MARKET
  if (served === null) return null
  if (selection === ALL_MARKETS) {
    return allowAll && served.length > 1 ? ALL_MARKETS : GPW_MARKET
  }
  return served.includes(selection) ? selection : GPW_MARKET
}
