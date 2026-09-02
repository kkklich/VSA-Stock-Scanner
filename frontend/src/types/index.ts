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
  /** 20-session median volume, in shares. */
  volume: number
  /** Sector from the GPW company list. */
  sector: string | null
  /** AI-insight engine confidence, 0–100. */
  aiConfidence: number
  /** % below the 52-week high (≤ 0; 0 = closed at the high). */
  distFrom52wHighPct: number | null
  /** % above the 52-week low (≥ 0). */
  distFrom52wLowPct: number | null
  /** The latest session set a new 52-week high / low. */
  isNew52wHigh: boolean
  isNew52wLow: boolean
  /** Per-method results keyed by method id (VSA + any registered method). */
  methodResults: Record<string, MethodResult>
  /** Mean of the selected methods' scores (0–100), or null. */
  combinedScore: number | null
  /** Whether the ticker is starred into the watchlist. */
  starred: boolean
}

/** One trading method's read of one stock — a cell in the multi-method list. */
export interface MethodResult {
  methodId: string
  /** 0–100 attractiveness for this method (feeds the combined score). */
  score: number
  /** Age in days of the last bar the setup fired on; 999 = not recently. */
  daysSince: number
  /** The setup fired on the most recent bar. */
  fired: boolean
  /** Short human note, e.g. the VSA verdict or "6/7 rules". */
  detail: string | null
  /** False when the stock has too little history to evaluate this method. */
  available: boolean
}

/** A selectable trading method in the dashboard's method picker. */
export interface TradingMethod {
  id: string
  name: string
  /** Plain-language explainer shown in the UI. */
  description: string
  /** Evidence source (book / paper / verified track record). */
  source: string
  sourceUrl: string | null
  /** "Bullish" — long-only setups for now. */
  direction: string
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

/** Fundamentals shown in the "Fundamentals" card. */
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
  /** 'Strength' or 'Weakness'. */
  side: 'Strength' | 'Weakness'
  name: string
  enabled: boolean
}

/** One row in the effectiveness statistics table. */
export interface EffectivenessRow {
  signal: string
  successPct: number
  /** null = undefined ratio (wins with no losses, or no judged trades). */
  rewardRisk: number | null
  /** Historical sample size the stats are computed from. */
  trades: number
}
