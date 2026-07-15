// Per-page SEO: updates the document <title>, meta description, social meta
// tags and canonical URL as the route changes. The crawlable initial HTML lives
// in index.html; this keeps the live tab + shared links accurate while the app
// runs (and helps when Googlebot renders JS).

import { useEffect } from 'react'

const BRAND = 'StockPilot'

type SeoEntry = { title: string; description: string }

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
    test: (p) => p.startsWith('/filters'),
    entry: {
      title: 'Filters',
      description:
        'VSA scanner filters: liquidity, market cap and other criteria for selecting GPW stocks.',
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
      // Per-ticker stock detail page.
      const ticker = (pathname.split('/')[2] ?? '').toUpperCase()
      entry = {
        title: ticker ? `${ticker} — VSA chart and signals` : 'VSA chart and signals',
        description: ticker
          ? `${ticker} candlestick chart with volume and Volume Spread Analysis (VSA) signals — VSA rating and signal history on the GPW.`
          : 'Interactive candlestick chart with Volume Spread Analysis (VSA) signals for a GPW stock.',
      }
    } else {
      entry = STATIC_ENTRIES.find((e) => e.test(pathname))?.entry ?? DEFAULT_ENTRY
    }

    const title = `${entry.title} | ${BRAND}`
    document.title = title
    setMetaByName('description', entry.description)
    setMetaByProperty('og:title', title)
    setMetaByProperty('og:description', entry.description)
    setMetaByName('twitter:title', title)
    setMetaByName('twitter:description', entry.description)

    // Canonical: replace the placeholder origin from index.html with the live
    // origin + current path so each route has a correct canonical URL.
    setCanonical(window.location.origin + pathname)
  }, [pathname])
}
