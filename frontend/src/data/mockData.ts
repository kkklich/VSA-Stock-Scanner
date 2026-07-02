// Mock-first datasets. Per CLAUDE.md we build and validate the UI against local
// mock JSON matching the API payloads before wiring real data. Replace these
// with calls to the ASP.NET Core API (/api/stocks/...) once the backend is live.

import type {
  Candle,
  EffectivenessRow,
  EngineRule,
  StockDetail,
  StockRankingItem,
  VsaSignal,
} from '../types'

const spark = (seed: number[]): number[] => seed

/** Watchlist / ranking table feed — mirrors GET /api/stocks/ranking. */
export const mockRanking: StockRankingItem[] = [
  {
    ticker: 'AAPL',
    name: 'Apple Inc.',
    lastPrice: 178.45,
    priceChangePct: 1.12,
    currentRating: 88,
    ratingChange: 3,
    lastSignal: 'Strong Buy',
    daysSinceSignal: 3,
    sparkline: spark([170, 172, 171, 174, 176, 175, 178]),
    starred: true,
  },
  {
    ticker: 'MSFT',
    name: 'Microsoft',
    lastPrice: 341.2,
    priceChangePct: 0.85,
    currentRating: 91,
    ratingChange: 4,
    lastSignal: 'Buy',
    daysSinceSignal: 1,
    sparkline: spark([330, 333, 332, 336, 338, 340, 341]),
    starred: true,
  },
  {
    ticker: 'TSLA',
    name: 'Tesla Inc.',
    lastPrice: 255.67,
    priceChangePct: -1.34,
    currentRating: 74,
    ratingChange: -2,
    lastSignal: 'Hold',
    daysSinceSignal: 5,
    sparkline: spark([262, 260, 261, 258, 257, 259, 255]),
    starred: false,
  },
  {
    ticker: 'NVDA',
    name: 'NVIDIA',
    lastPrice: 492.3,
    priceChangePct: 2.1,
    currentRating: 95,
    ratingChange: 2,
    lastSignal: 'Strong Buy',
    daysSinceSignal: 2,
    sparkline: spark([470, 475, 478, 482, 485, 488, 492]),
    starred: true,
  },
  {
    ticker: 'AMZN',
    name: 'Amazon',
    lastPrice: 142.11,
    priceChangePct: 0.98,
    currentRating: 82,
    ratingChange: 1,
    lastSignal: 'Buy',
    daysSinceSignal: 4,
    sparkline: spark([138, 139, 140, 139, 141, 140, 142]),
    starred: false,
  },
  {
    ticker: 'GOOGL',
    name: 'Alphabet A',
    lastPrice: 139.75,
    priceChangePct: 0.55,
    currentRating: 85,
    ratingChange: 2,
    lastSignal: 'Buy',
    daysSinceSignal: 6,
    sparkline: spark([136, 137, 138, 137, 139, 138, 139]),
    starred: false,
  },
  {
    ticker: 'META',
    name: 'Meta Platforms',
    lastPrice: 315.4,
    priceChangePct: -0.62,
    currentRating: 71,
    ratingChange: -1,
    lastSignal: 'Hold',
    daysSinceSignal: 8,
    sparkline: spark([320, 319, 318, 317, 316, 317, 315]),
    starred: false,
  },
  {
    ticker: 'NFLX',
    name: 'Netflix Inc.',
    lastPrice: 465.8,
    priceChangePct: 1.78,
    currentRating: 89,
    ratingChange: 5,
    lastSignal: 'Buy',
    daysSinceSignal: 1,
    sparkline: spark([452, 455, 458, 460, 462, 464, 465]),
    starred: true,
  },
]

/** Deterministic candlestick series so the chart looks stable across reloads. */
function buildCandles(): Candle[] {
  const out: Candle[] = []
  let price = 430
  const start = new Date('2026-04-15')
  for (let i = 0; i < 60; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    // Skip weekends to look like trading days.
    if (d.getDay() === 0 || d.getDay() === 6) continue
    const drift = Math.sin(i / 6) * 6 + (i > 35 ? (i - 35) * 1.4 : 0)
    const noise = Math.sin(i * 3.7) * 4
    const open = price
    const close = price + drift * 0.4 + noise
    const high = Math.max(open, close) + Math.abs(noise) + 3
    const low = Math.min(open, close) - Math.abs(noise) - 3
    const volume = 80_000 + Math.abs(Math.sin(i * 2.3)) * 220_000
    out.push({
      time: d.toISOString().slice(0, 10),
      open: +open.toFixed(2),
      high: +high.toFixed(2),
      low: +low.toFixed(2),
      close: +close.toFixed(2),
      volume: Math.round(volume),
    })
    price = close
  }
  return out
}

const nvdaCandles = buildCandles()

const nvdaSignals: VsaSignal[] = [
  { date: nvdaCandles[8].time, signalName: 'SPRING', type: 'Bullish' },
  { date: nvdaCandles[22].time, signalName: 'TEST', type: 'Bullish' },
  { date: nvdaCandles[30].time, signalName: 'UPTHRUST', type: 'Bearish' },
  { date: nvdaCandles[34].time, signalName: 'UPTHRUST', type: 'Bearish' },
  { date: nvdaCandles[40].time, signalName: 'SOS', type: 'Bullish' },
]

/** Detailed feed for the charts page — mirrors GET /api/stocks/{ticker}/signals. */
export const mockDetail: StockDetail = {
  ticker: 'NVDA',
  name: 'NVIDIA',
  lastPrice: 492.3,
  priceChangePct: 2.1,
  currentRating: 95,
  ratingChange: 2,
  fundamentals: {
    sector: 'Technology',
    industry: 'Semiconductors',
    marketCap: '$1.21 T',
  },
  strength: [
    { name: 'Stopping Volume', present: true, date: '2026-05-15' },
    { name: 'Spring', present: true, date: '2026-05-15' },
    { name: 'Test', present: true, date: '2026-05-18' },
    { name: 'Successful Test', present: true, date: '2026-05-21' },
    { name: 'Shakeout', present: false, date: '—' },
    { name: 'Bag Holding', present: true, date: '2026-05-24' },
    { name: 'Sign of Strength', present: true, date: '2026-06-02' },
  ],
  weakness: [
    { name: 'Upthrust', present: false, date: '—' },
    { name: 'No Demand', present: false, date: '—' },
    { name: 'Buying Climax', present: true, date: '2026-06-12' },
    { name: 'Sign of Weakness', present: false, date: '—' },
    { name: 'End of Rising Market', present: true, date: '2026-06-20' },
  ],
  candles: nvdaCandles,
  signals: nvdaSignals,
}

/** Side panel watchlist mini-list on the detail page. */
export const mockMiniWatchlist = [
  { ticker: 'NVDA', rating: 95, ratingChange: 2 },
  { ticker: 'MSFT', rating: 91, ratingChange: 4 },
  { ticker: 'NFLX', rating: 89, ratingChange: 5 },
  { ticker: 'AAPL', rating: 88, ratingChange: 3 },
]

/**
 * Scanner "Silnik VSA" rule toggles — the canonical set of detectable VSA
 * signals. Names are unique and align 1:1 with mockEffectiveness below so the
 * engine list, the per-signal tuner, and the stats table stay in sync.
 */
export const mockEngineRules: EngineRule[] = [
  { id: 'spring', side: 'Siła', name: 'Spring', enabled: true },
  { id: 'sos', side: 'Siła', name: 'Sign of Strength', enabled: true },
  { id: 'test', side: 'Siła', name: 'Test', enabled: true },
  { id: 'shakeout', side: 'Siła', name: 'Shakeout', enabled: false },
  { id: 'upthrust', side: 'Słabość', name: 'Upthrust', enabled: true },
  { id: 'nodemand', side: 'Słabość', name: 'No Demand', enabled: true },
  { id: 'sow', side: 'Słabość', name: 'Sign of Weakness', enabled: false },
]

/** Effectiveness statistics table + donut. Keyed by the same signal names. */
export const mockEffectiveness: EffectivenessRow[] = [
  { signal: 'Spring', successPct: 67, rewardRisk: 2.7, trades: 142 },
  { signal: 'Sign of Strength', successPct: 64, rewardRisk: 2.3, trades: 98 },
  { signal: 'Test', successPct: 62, rewardRisk: 1.9, trades: 120 },
  { signal: 'Shakeout', successPct: 71, rewardRisk: 1.2, trades: 54 },
  { signal: 'Upthrust', successPct: 59, rewardRisk: 1.1, trades: 110 },
  { signal: 'No Demand', successPct: 66, rewardRisk: 0.8, trades: 88 },
  { signal: 'Sign of Weakness', successPct: 61, rewardRisk: 1.4, trades: 73 },
]

/** Last end-of-day ingestion timestamp shown in the top bar. */
export const lastSyncLabel = '2026-06-29 17:35'
