// Per-page SEO: updates the document <title>, meta description, social meta
// tags and canonical URL as the route changes. The crawlable initial HTML lives
// in index.html; this keeps the live tab + shared links accurate while the app
// runs (and helps when Googlebot renders JS).

import { useEffect } from 'react'

const BRAND = 'StockPilot'

type SeoEntry = { title: string; description: string }

const DEFAULT_ENTRY: SeoEntry = {
  title: 'Skaner VSA dla GPW',
  description:
    'Skaner Volume Spread Analysis (VSA) dla Giełdy Papierów Wartościowych (GPW): ranking spółek, wykresy i sygnały.',
}

const STATIC_ENTRIES: { test: (p: string) => boolean; entry: SeoEntry }[] = [
  {
    test: (p) => p === '/',
    entry: {
      title: 'Pulpit VSA — GPW',
      description:
        'Najlepsze spółki GPW według metody VSA, dzienni liderzy wzrostów i spadków oraz Twoje ulubione spółki — w jednym pulpicie StockPilot.',
    },
  },
  {
    test: (p) => p.startsWith('/watchlist'),
    entry: {
      title: 'Watchlista GPW — ranking VSA',
      description:
        'Twoja watchlista i ranking spółek GPW według oceny VSA 0–100: cena, sygnał, dni od sygnału i zmiana. Skaner Volume Spread Analysis StockPilot.',
    },
  },
  {
    test: (p) => p.startsWith('/scanner'),
    entry: {
      title: 'Skaner VSA GPW',
      description:
        'Konfiguruj silnik VSA i progi detekcji sygnałów (Spring, Upthrust, No Demand, SOS) oraz sprawdź statystyki skuteczności na GPW.',
    },
  },
  {
    test: (p) => p.startsWith('/filters'),
    entry: {
      title: 'Filtry',
      description:
        'Filtry skanera VSA: płynność, kapitalizacja i inne kryteria doboru spółek GPW.',
    },
  },
  {
    test: (p) => p.startsWith('/settings'),
    entry: {
      title: 'Ustawienia',
      description: 'Ustawienia aplikacji StockPilot — skanera VSA dla GPW.',
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
        title: ticker ? `${ticker} — wykres i sygnały VSA` : 'Wykres i sygnały VSA',
        description: ticker
          ? `Wykres świecowy ${ticker} z wolumenem i sygnałami Volume Spread Analysis (VSA) — ocena VSA i historia sygnałów na GPW.`
          : 'Interaktywny wykres świecowy z sygnałami Volume Spread Analysis (VSA) dla spółki z GPW.',
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
