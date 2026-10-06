// Per-page SEO: updates the document <title>, meta description, social meta
// tags and canonical URL as the route changes. The crawlable initial HTML lives
// in index.html; this keeps the live tab + shared links accurate while the app
// runs (and helps when Googlebot renders JS).

import { useEffect } from 'react'
import { displayTicker, marketOfTicker } from './markets'

const BRAND = 'StockPilot'

type SeoEntry = {
  title: string
  description: string
  /** Keep this page out of search results. Set for operational screens that
   *  are of no use to a visitor and should not be indexed. */
  noindex?: boolean
}

const DEFAULT_ENTRY: SeoEntry = {
  title: 'VSA Scanner for the GPW',
  description:
    'Volume Spread Analysis (VSA) scanner for the Warsaw Stock Exchange (GPW): stock ranking, charts and signals.',
}

const STATIC_ENTRIES: { test: (p: string) => boolean; entry: SeoEntry }[] = [
  {
    test: (p) => p === '/',
    entry: {
      title: 'VSA Dashboard — GPW',
      description:
        'The best GPW stocks by the VSA method, the day\'s top gainers and losers, and your favorite stocks — in one StockPilot dashboard.',
    },
  },
  {
    test: (p) => p.startsWith('/watchlist'),
    entry: {
      title: 'GPW Watchlist — VSA ranking',
      description:
        'Your watchlist and the GPW stock ranking by VSA rating 0–100: price, signal, days since signal and change. StockPilot Volume Spread Analysis scanner.',
    },
  },
  {
    test: (p) => p.startsWith('/scanner'),
    entry: {
      title: 'GPW VSA Scanner',
      description:
        'Configure the VSA engine and signal-detection thresholds (Spring, Upthrust, No Demand, SOS) and review effectiveness statistics on the GPW.',
    },
  },
  {
    test: (p) => p.startsWith('/heatmap'),
    entry: {
      title: 'GPW Sector Heatmap',
      description:
        'Finviz-style sector heatmap of GPW stocks: tile size = market cap, color = VSA rating or price change over 1 day, 1 month, 1 year or the full history.',
    },
  },
  {
    test: (p) => p.startsWith('/volume-surge'),
    entry: {
      title: 'GPW Volume Surge — unusual volume scanner',
      description:
        'GPW stocks trading on unusually high volume: relative volume (RVOL) over the last sessions vs the stock\'s own baseline, with VSA rating and signal context.',
    },
  },
  {
    test: (p) => p.startsWith('/capex'),
    entry: {
      title: 'GPW Investment Spending — capex by company',
      description:
        'How much each GPW-listed company invests in its own business: capital expenditure over the last twelve months, year-on-year change, and capex as a share of revenue and operating cash flow.',
    },
  },
  {
    test: (p) => p.startsWith('/filters'),
    entry: {
      title: 'GPW Stock Screener — filters and saved presets',
      description:
        'Screen GPW stocks by sector, VSA rating band, signal and its age, price range and liquidity — and save filter combinations as one-click presets.',
    },
  },
  {
    test: (p) => p === '/education' || p === '/education/',
    entry: {
      title: 'Education — how the trading methods work',
      description:
        "StockPilot's knowledge base: what each trading method in the app looks for, where it comes from and how to read its signals — VSA, Minervini, Weinstein, Volume Breakout and more. In Polish and English.",
    },
  },
  {
    test: (p) => p.startsWith('/education/vsa-rating'),
    entry: {
      title: 'The VSA rating — how the 0–100 score works',
      description:
        "How StockPilot's VSA rating is calculated: the six volume patterns (Spring, Sign of Strength, Test, Upthrust, Sign of Weakness, No Demand), time decay, the verdict, and how well it has worked.",
    },
  },
  {
    test: (p) => p.startsWith('/education/minervini'),
    entry: {
      title: 'Minervini Trend Template — the eight rules explained',
      description:
        "Mark Minervini's Trend Template as StockPilot checks it: moving averages, the 52-week range, relative strength, what the score means and the measured results on the GPW.",
    },
  },
  {
    test: (p) => p.startsWith('/education/volume-breakout'),
    entry: {
      title: 'Volume Breakout — buying a base breakout on volume',
      description:
        "The base breakout of William O'Neil (CANSLIM) and Mark Minervini (VCP) as StockPilot checks it: new high, volume surge, a quiet tight base, the readiness score and the measured results.",
    },
  },
  {
    test: (p) => p.startsWith('/education/weinstein'),
    entry: {
      title: 'Weinstein Stage 2 — the Stage 1 to Stage 2 breakout',
      description:
        "Stan Weinstein's stage analysis on the weekly chart as StockPilot checks it: the 30-week moving average, the base, the 2x volume test, a real GPW example and the measured results.",
    },
  },
  {
    test: (p) => p.startsWith('/education/pocket-pivot'),
    entry: {
      title: 'Pocket Pivot — an early volume buy inside the base',
      description:
        "Gil Morales and Chris Kacher's pocket pivot as StockPilot checks it: up-day volume against the heaviest recent down day, the 10- and 50-day lines, real GPW examples and the measured results.",
    },
  },
  {
    test: (p) => p.startsWith('/education/vsa-kompendium') || p.startsWith('/vsa-kompendium'),
    entry: {
      title: 'VSA Kompendium — price and volume analysis',
      description:
        'The full Volume Spread Analysis compendium behind StockPilot\'s VSA V4 method: bar anatomy, the signal catalogue, sequences, WFO, risk and the code formalisation.',
    },
  },
  {
    test: (p) => p.startsWith('/legal'),
    entry: {
      title: 'Legal information — disclaimer, terms and privacy',
      description:
        'StockPilot legal information: what the automated VSA ratings are and are not (they are not investment advice), the publisher and contact details, the terms of service and the privacy policy.',
    },
  },
  {
    test: (p) => p.startsWith('/system'),
    entry: {
      title: 'System status',
      description:
        'Operational status of the StockPilot backend: the last data refresh, how current the stored data is, and recent errors.',
      noindex: true,
    },
  },
  {
    test: (p) => p.startsWith('/login'),
    entry: {
      title: 'Sign in',
      description:
        'Sign in to StockPilot or create an account. An account is optional — every page works without one.',
      // Nothing for a search engine here, and a sign-in form in the results
      // is a phishing target: keep it out of the index like /system.
      noindex: true,
    },
  },
  {
    test: (p) => p.startsWith('/settings'),
    entry: {
      title: 'Settings',
      description: 'StockPilot settings — the VSA scanner for the GPW.',
    },
  },
]

/** Create-or-update a <meta name="..."> tag. */
function setMetaByName(name: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

/** Create-or-update a <meta property="..."> tag (Open Graph). */
function setMetaByProperty(property: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(
    `meta[property="${property}"]`,
  )
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('property', property)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

/** Where a market's stocks trade, as the stock-page description names it. */
const MARKET_VENUES: Record<string, string> = {
  gpw: 'the GPW',
  us: 'NASDAQ / NYSE',
  de: 'Xetra',
  fr: 'Euronext Paris',
  nl: 'Euronext Amsterdam',
  uk: 'the London Stock Exchange',
}

/** Create-or-update the canonical <link>. */
function setCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', 'canonical')
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

export function usePageSeo(pathname: string) {
  useEffect(() => {
    let entry = DEFAULT_ENTRY

    if (pathname.startsWith('/stock/')) {
      // Per-ticker stock detail page. A foreign ticker's suffix names its
      // market, so the text says where the stock trades.
      const raw = decodeURIComponent(pathname.split('/')[2] ?? '')
      const ticker = displayTicker(raw).toUpperCase()
      const venue = MARKET_VENUES[marketOfTicker(raw)] ?? MARKET_VENUES.gpw
      entry = {
        title: ticker ? `${ticker} — VSA chart and signals` : 'VSA chart and signals',
        description: ticker
          ? `${ticker} candlestick chart with volume and Volume Spread Analysis (VSA) signals — VSA rating and signal history on ${venue}.`
          : 'Interactive candlestick chart with Volume Spread Analysis (VSA) signals for a listed stock.',
      }
    } else {
      entry = STATIC_ENTRIES.find((e) => e.test(pathname))?.entry ?? DEFAULT_ENTRY
    }

    const title = `${entry.title} | ${BRAND}`
    document.title = title
    setMetaByName('description', entry.description)
    // index.html ships "index, follow"; an operational page overrides it, and
    // every other route puts it back on the way out.
    setMetaByName(
      'robots',
      entry.noindex ? 'noindex, nofollow' : 'index, follow, max-image-preview:large',
    )
    setMetaByProperty('og:title', title)
    setMetaByProperty('og:description', entry.description)
    setMetaByName('twitter:title', title)
    setMetaByName('twitter:description', entry.description)

    // Canonical: replace the placeholder origin from index.html with the live
    // origin + current path so each route has a correct canonical URL.
    setCanonical(window.location.origin + pathname)
  }, [pathname])
}
