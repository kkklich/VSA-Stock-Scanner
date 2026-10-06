import { describe, expect, it } from 'vitest'
import type { ApiVolumeSurgeItem } from '../api/stocksApi'
import {
  closeClass,
  describePeakBar,
  fmtSessionDay,
  peakBarDetail,
  signalAge,
  signalAgeLabel,
  signalAgeText,
  spreadClass,
} from './volumeSurge'

function item(over: Partial<ApiVolumeSurgeItem> = {}): ApiVolumeSurgeItem {
  return {
    ticker: 'KGH',
    name: 'KGHM',
    sector: 'Mining',
    market: 'gpw',
    currency: 'PLN',
    lastPrice: 150,
    recentAvgVolume: 300_000,
    baselineAvgVolume: 100_000,
    volumeRatio: 3,
    lastDayRatio: 3,
    daysAboveBaseline: 3,
    priceChangePct: 4,
    currentRating: 70,
    lastSignal: 'Buy',
    daysSinceSignal: 1,
    signalInWindow: true,
    surgeStart: '2026-09-23',
    peakDate: '2026-09-24',
    peakVolumeRatio: 4.2,
    peakChangePct: 3.1,
    peakSpreadRatio: 2,
    peakClosePosition: 0.9,
    breaksHigh: true,
    breaksLow: false,
    reportDate: null,
    ...over,
  }
}

describe('spreadClass', () => {
  it('uses the VSA engine thresholds', () => {
    expect(spreadClass(1.5)).toBe('wide')
    expect(spreadClass(1.49)).toBe('average')
    expect(spreadClass(0.71)).toBe('average')
    expect(spreadClass(0.7)).toBe('narrow')
    expect(spreadClass(null)).toBeNull()
  })
})

describe('closeClass', () => {
  it('reads the close in thirds of the range', () => {
    expect(closeClass(1)).toBe('high')
    expect(closeClass(0.67)).toBe('high')
    expect(closeClass(0.5)).toBe('middle')
    expect(closeClass(0.33)).toBe('low')
    expect(closeClass(0)).toBe('low')
    expect(closeClass(null)).toBeNull()
  })
})

describe('describePeakBar', () => {
  it('names the spread and the close', () => {
    expect(describePeakBar(item())).toBe('Wide, closed high')
    expect(
      describePeakBar(item({ peakSpreadRatio: 0.5, peakClosePosition: 0.1 })),
    ).toBe('Narrow, closed low')
    expect(
      describePeakBar(item({ peakSpreadRatio: 1, peakClosePosition: 0.5 })),
    ).toBe('Average, closed mid')
  })

  it('drops the spread when there is no reference for it', () => {
    expect(describePeakBar(item({ peakSpreadRatio: null }))).toBe('Closed high')
  })

  it('says so when the bar had no range at all', () => {
    expect(describePeakBar(item({ peakClosePosition: null }))).toBe('No price range')
  })

  it('spells out the numbers for the tooltip', () => {
    expect(peakBarDetail(item())).toBe(
      "Busiest session Thu 24.09: 4.2× a typical day's volume, spread 2.0× the reference average, closed at 90% of its range, +3.10% on the day.",
    )
    expect(
      peakBarDetail(item({ peakSpreadRatio: null, peakClosePosition: null, peakChangePct: -1 })),
    ).toContain('no reference spread, no price range, -1.00% on the day')
  })
})

describe('fmtSessionDay', () => {
  it('prints the weekday and the Polish day.month', () => {
    expect(fmtSessionDay('2026-09-24')).toBe('Thu 24.09')
    expect(fmtSessionDay('2026-01-05')).toBe('Mon 05.01')
  })
})

describe('signalAge', () => {
  it('tells a signal in the surge from an older one', () => {
    expect(signalAge(item())).toEqual({ kind: 'inSurge', days: 1 })
    expect(signalAge(item({ signalInWindow: false, daysSinceSignal: 23 }))).toEqual({
      kind: 'beforeSurge',
      days: 23,
    })
    expect(signalAge(item({ daysSinceSignal: 999, signalInWindow: false }))).toEqual({
      kind: 'none',
    })
  })

  it('gives the badge a short label', () => {
    expect(signalAgeLabel(item())).toBe('signal in the surge')
    expect(signalAgeLabel(item({ signalInWindow: false, daysSinceSignal: 23 }))).toBe(
      'last signal 23 d ago',
    )
    expect(signalAgeLabel(item({ daysSinceSignal: 999 }))).toBe('no recent signal')
  })

  it('writes it out in plain words', () => {
    expect(signalAgeText(item())).toBe('Signal 1 d ago, during the surge')
    expect(signalAgeText(item({ daysSinceSignal: 0 }))).toBe(
      'Signal on the last session, during the surge',
    )
    expect(signalAgeText(item({ signalInWindow: false, daysSinceSignal: 23 }))).toBe(
      'Last signal 23 d ago, before the surge',
    )
    expect(signalAgeText(item({ daysSinceSignal: 999 }))).toBe(
      'No VSA signal in the last 4 months',
    )
  })
})
