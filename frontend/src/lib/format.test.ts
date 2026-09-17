import { describe, it, expect } from 'vitest'
import {
  currencyLabel,
  deltaTone,
  fmtCompactPln,
  fmtMoney,
  fmtPct,
  fmtPrice,
  fmtRefreshTime,
  fmtSigned,
  majorCurrency,
  ratingTone,
} from './format'

describe('currencies', () => {
  it('writes pence the way brokers do', () => {
    expect(currencyLabel('GBp')).toBe('GBX')
    expect(currencyLabel('USD')).toBe('USD')
    // An older payload without a currency is a złoty one.
    expect(currencyLabel(undefined)).toBe('PLN')
  })

  it('puts the currency after the price', () => {
    expect(fmtMoney(331.65, 'PLN')).toBe('331.65 PLN')
    expect(fmtMoney(1507.8, 'GBp')).toBe('1,507.80 GBX')
    expect(fmtMoney(332.86)).toBe('332.86 PLN')
  })

  it('states whole amounts in pounds, not pence', () => {
    expect(majorCurrency('GBp')).toBe('GBP')
    expect(majorCurrency('EUR')).toBe('EUR')
    expect(majorCurrency(null)).toBe('PLN')
  })
})

describe('fmtPrice', () => {
  it('always shows two decimals', () => {
    expect(fmtPrice(12)).toBe('12.00')
    expect(fmtPrice(12.5)).toBe('12.50')
    expect(fmtPrice(12.345)).toBe('12.35')
  })

  it('groups thousands', () => {
    expect(fmtPrice(1234567.8)).toBe('1,234,567.80')
  })
})

describe('fmtPct', () => {
  it('prefixes a sign and appends a percent', () => {
    expect(fmtPct(1.123)).toBe('+1.12%')
    expect(fmtPct(-0.62)).toBe('-0.62%')
    expect(fmtPct(0)).toBe('+0.00%')
  })
})

describe('fmtSigned', () => {
  it('shows an explicit + for non-negative integers', () => {
    expect(fmtSigned(2)).toBe('+2')
    expect(fmtSigned(0)).toBe('+0')
    expect(fmtSigned(-1)).toBe('-1')
  })
})

describe('fmtCompactPln', () => {
  it('compacts by magnitude', () => {
    expect(fmtCompactPln(3_420_000_000)).toBe('3.42 B')
    expect(fmtCompactPln(319_000_000)).toBe('319 M')
    expect(fmtCompactPln(5_000)).toBe('5 K')
    expect(fmtCompactPln(750)).toBe('750')
  })
})

describe('ratingTone', () => {
  it('is emerald above 70, rose below 30, slate in between', () => {
    expect(ratingTone(85).text).toContain('emerald')
    expect(ratingTone(15).text).toContain('rose')
    expect(ratingTone(50).text).toContain('slate')
  })

  it('treats the 70 and 30 boundaries as neutral', () => {
    expect(ratingTone(70).text).toContain('slate')
    expect(ratingTone(30).text).toContain('slate')
  })
})

describe('deltaTone', () => {
  it('colors by direction', () => {
    expect(deltaTone(1)).toContain('emerald')
    expect(deltaTone(-1)).toContain('rose')
    expect(deltaTone(0)).toContain('slate')
  })
})

describe('fmtRefreshTime', () => {
  it('uses the caller\'s word for "today"', () => {
    const now = new Date().toISOString()
    expect(fmtRefreshTime(now, 'dziś')).toMatch(/^dziś \d{2}:\d{2}$/)
    expect(fmtRefreshTime(now)).toMatch(/^today \d{2}:\d{2}$/)
  })

  it('shows the day for an older refresh and a dash for garbage', () => {
    expect(fmtRefreshTime('2020-03-04T12:00:00Z', 'dziś')).toMatch(/^04\.03 \d{2}:\d{2}$/)
    expect(fmtRefreshTime('not a date')).toBe('—')
  })
})
