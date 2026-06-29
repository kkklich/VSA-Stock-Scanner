// Shared domain types for StockPilot. Mirrors the API payloads documented in
// agent/DOCUMENTATION.md §5. Keep this file the single source of truth for
// shared shapes (no `any`).

/** A row in the ranking / watchlist table. */
export interface StockRankingItem {
  ticker: string
  name: string
  /** Last traded price in PLN. */
  lastPrice: number
  /** Intraday price change, percent. */
  priceChangePct: number
  /** Computed VSA rating, 0–100. */
  currentRating: number
  /** Day-over-day rating change. */
  ratingChange: number
  /** Most recent signal verdict shown as a badge. */
  lastSignal: SignalVerdict
  /** Days elapsed since lastSignal fired (Time Decay calibration). */
  daysSinceSignal: number
  /** Tiny price series used to draw the row sparkline. */
  sparkline: number[]
  /** Whether the ticker is starred into the watchlist. */
  starred: boolean
}

/** The badge verdict derived from the strongest active VSA structure. */
export type SignalVerdict = 'Strong Buy' | 'Buy' | 'Hold' | 'Sell' | 'Strong Sell'

/** One OHLCV bar for the candlestick chart. */
export interface Candle {
  time: string // YYYY-MM-DD
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/** A detected VSA structure plotted as a chart marker. */
export interface VsaSignal {
  date: string
  signalName: string
  type: 'Bullish' | 'Bearish'
}

/** A row in the strength / weakness signal checklist (detail view). */
export interface SignalFlag {
  name: string
  /** Whether the pattern was detected for this asset. */
  present: boolean
  date: string
}

/** Fundamentals shown in the "Dane podstawowe" card. */
export interface StockFundamentals {
  sector: string
  industry: string
  marketCap: string
}

/** Aggregated detail payload for a single ticker (detail / charts page). */
export interface StockDetail {
  ticker: string
  name: string
  lastPrice: number
  priceChangePct: number
  currentRating: number
  ratingChange: number
  fundamentals: StockFundamentals
  strength: SignalFlag[]
  weakness: SignalFlag[]
  candles: Candle[]
  signals: VsaSignal[]
}

/** A toggleable rule in the scanner's VSA engine list. */
export interface EngineRule {
  id: string
  /** 'Siła' (strength) or 'Słabość' (weakness). */
  side: 'Siła' | 'Słabość'
  name: string
  enabled: boolean
}

/** One row in the effectiveness statistics table. */
export interface EffectivenessRow {
  signal: string
  successPct: number
  rewardRisk: number
}
