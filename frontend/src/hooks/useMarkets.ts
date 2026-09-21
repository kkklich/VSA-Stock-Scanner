// The markets this deployment serves (GET /api/stocks/markets), fetched once
// per page load and shared by every component that asks — the switcher in the
// top bar and the pages that scope their data by market.
//
// A backend that predates markets (404) or cannot be reached is treated as a
// GPW-only deployment, which is exactly what it is.

import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
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

/** How long to wait before asking again when the backend did not answer. */
export const MARKETS_RETRY_MS = 30_000

interface Catalogue {
  markets: ApiMarket[]
  /** The backend did not answer (down, restarting) — worth asking again. */
  retry: boolean
}

let shared: Promise<Catalogue> | null = null

/** "Not answering yet" (no connection, a gateway error), not "no such endpoint". */
function isTransient(err: unknown): boolean {
  return !(err instanceof ApiError) || err.status === 0 || err.status >= 500
}

function loadMarkets(): Promise<Catalogue> {
  if (shared === null) {
    shared = fetchMarkets()
      .then((list) => ({ markets: list.length > 0 ? list : GPW_ONLY, retry: false }))
      .catch((err: unknown) => {
        // Answer GPW-only for now, but forget the failure so the next ask goes
        // back to the backend — one that was restarting must not hide the
        // other markets for the rest of the session.
        shared = null
        return { markets: GPW_ONLY, retry: isTransient(err) }
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
    let timer: ReturnType<typeof setTimeout> | undefined
    const ask = () => {
      void loadMarkets().then(({ markets: list, retry }) => {
        if (cancelled) return
        setMarkets(list)
        // The top bar's switcher is mounted once per page load, so "the next
        // component to mount asks again" never reaches it: a backend that did
        // not answer is asked again from here until it does.
        if (retry) timer = setTimeout(ask, MARKETS_RETRY_MS)
      })
    }
    ask()
    return () => {
      cancelled = true
      clearTimeout(timer)
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
