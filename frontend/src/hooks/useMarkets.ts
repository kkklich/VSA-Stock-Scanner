// The markets this deployment serves (GET /api/stocks/markets), fetched once
// per page load and shared by every component that asks — the switcher in the
// top bar and the pages that scope their data by market.
//
// A backend that predates markets (404) or cannot be reached is treated as a
// GPW-only deployment, which is exactly what it is.

import { useEffect, useState } from 'react'
import { fetchMarkets, type ApiMarket } from '../api/stocksApi'
import {
  ALL_MARKETS,
  effectiveMarket,
  GPW_MARKET,
  useMarketSelection,
  type MarketSelection,
} from '../lib/markets'

/** What a GPW-only deployment looks like, for backends without the catalogue. */
export const GPW_ONLY: ApiMarket[] = [
  {
    id: GPW_MARKET,
    name: 'Warsaw Stock Exchange',
    shortName: 'GPW',
    country: 'Poland',
    region: 'poland',
    exchange: 'GPW',
    currency: 'PLN',
    majorCurrency: 'PLN',
    timezone: 'Europe/Warsaw',
    tickerSuffix: '',
    refreshRun: 'europe',
    companyCount: 0,
    indices: [],
  },
]

let shared: Promise<ApiMarket[]> | null = null

function loadMarkets(): Promise<ApiMarket[]> {
  if (shared === null) {
    shared = fetchMarkets()
      .then((list) => (list.length > 0 ? list : GPW_ONLY))
      .catch(() => {
        // Answer GPW-only for now, but let the next component that mounts ask
        // again — a backend that was restarting must not hide the other
        // markets for the rest of the session.
        shared = null
        return GPW_ONLY
      })
  }
  return shared
}

/** Forget the cached catalogue (tests). */
export function resetMarketsCache(): void {
  shared = null
}

/**
 * The served markets, or null while they load. With `enabled: false` nothing
 * is fetched and the answer stays null — for callers that already know they
 * only need the GPW.
 */
export function useMarkets({ enabled = true }: { enabled?: boolean } = {}): ApiMarket[] | null {
  const [markets, setMarkets] = useState<ApiMarket[] | null>(null)
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    void loadMarkets().then((list) => {
      if (!cancelled) setMarkets(list)
    })
    return () => {
      cancelled = true
    }
  }, [enabled])
  return markets
}

/**
 * The market a list page should request right now, from the user's choice and
 * the served catalogue (see `effectiveMarket`). Null only while a non-default
 * choice waits for the catalogue — the page should hold its request until then.
 */
export function useMarketScope({ allowAll }: { allowAll: boolean }): {
  market: MarketSelection | null
  markets: ApiMarket[] | null
} {
  const { selection } = useMarketSelection()
  const markets = useMarkets({ enabled: selection !== GPW_MARKET })
  const served = markets ? markets.map((m) => m.id) : null
  return { market: effectiveMarket(selection, served, { allowAll }), markets }
}

/**
 * For screens that show one market at a time (the heatmap sizes tiles by
 * market cap, the capex list sorts money): the top bar's market when it names
 * one; when it says "All markets", a choice the page keeps itself (default:
 * the GPW), offered through its own picker.
 */
export function useSingleMarket(): {
  market: string | null
  markets: ApiMarket[] | null
  /** The page should show its own market picker. */
  needsPicker: boolean
  pick: (id: string) => void
} {
  const { selection } = useMarketSelection()
  const markets = useMarkets({ enabled: selection !== GPW_MARKET })
  const [local, setLocal] = useState<string>(GPW_MARKET)
  const served = markets ? markets.map((m) => m.id) : null
  if (selection === ALL_MARKETS) {
    return {
      market: served === null ? null : served.includes(local) ? local : GPW_MARKET,
      markets,
      needsPicker: (served?.length ?? 0) > 1,
      pick: setLocal,
    }
  }
  return {
    market: effectiveMarket(selection, served, { allowAll: false }),
    markets,
    needsPicker: false,
    pick: setLocal,
  }
}
