// Small formatting + color helpers shared across the UI.

/** Format a number as a price with two decimals. */
export const fmtPrice = (n: number): string =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/**
 * How a currency is written next to an amount. Yahoo's "GBp" (London prices
 * quoted in pence) is written GBX, the way Polish brokers show it; anything
 * unknown is shown as given, and a missing one is the app's home currency.
 */
export function currencyLabel(currency: string | null | undefined): string {
  if (!currency) return 'PLN'
  if (currency === 'GBp' || currency === 'GBX') return 'GBX'
  return currency
}

/** A price with its currency: "331.65 PLN", "332.86 USD", "1,507.80 GBX". */
export const fmtMoney = (n: number, currency?: string | null): string =>
  `${fmtPrice(n)} ${currencyLabel(currency)}`

/** The currency whole amounts (a market cap) are stated in — GBP for pence. */
export function majorCurrency(currency: string | null | undefined): string {
  if (!currency) return 'PLN'
  return currency === 'GBp' || currency === 'GBX' ? 'GBP' : currency
}

/** Signed percent, e.g. +1.12% / -0.62%. */
export const fmtPct = (n: number): string => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`

/** Signed integer, e.g. +2 / -1. */
export const fmtSigned = (n: number): string => `${n >= 0 ? '+' : ''}${n}`

/** Large amounts in compact form, e.g. "3.42 B" / "319 M" (add the currency yourself). */
export const fmtCompactPln = (n: number): string => {
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)} B`
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(0)} M`
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(0)} K`
  return n.toLocaleString('en-US')
}

/**
 * VSA rating badge color band (per DOCUMENTATION.md §4):
 *  > 70 green, < 30 red, otherwise neutral slate.
 */
export function ratingTone(rating: number): {
  text: string
  bar: string
  badge: string
} {
  if (rating > 70)
    return {
      text: 'text-emerald-400',
      bar: 'bg-emerald-500',
      badge: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
    }
  if (rating < 30)
    return {
      text: 'text-rose-400',
      bar: 'bg-rose-500',
      badge: 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
    }
  return {
    text: 'text-slate-300',
    bar: 'bg-slate-400',
    badge: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
  }
}

/**
 * Compact timestamp for the refresh status: "today 18:02" or "12.07 18:02".
 * `todayLabel` is the translated word for "today" — the caller has `t()`.
 */
export const fmtRefreshTime = (iso: string, todayLabel = 'today'): string => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const time = d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })
  const today = new Date()
  const sameDay =
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  if (sameDay) return `${todayLabel} ${time}`
  const day = d.toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })
  return `${day} ${time}`
}

/** Directional text color for a numeric delta. */
export const deltaTone = (n: number): string =>
  n > 0 ? 'text-emerald-400' : n < 0 ? 'text-rose-400' : 'text-slate-400'

/**
 * Return `url` only if it is a well-formed http(s) URL, otherwise `null`.
 *
 * Used before putting an externally-sourced value into an `<a href>`. React
 * does not sanitise href, so a `javascript:` / `data:` URL there would run on
 * click. Company websites come from curated data today, but validating the
 * scheme keeps that one link safe no matter where the value originates.
 */
export function safeHttpUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? url : null
  } catch {
    return null
  }
}
