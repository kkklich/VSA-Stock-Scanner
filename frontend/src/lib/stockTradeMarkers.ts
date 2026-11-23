import type { StockTrade } from '../api/portfoliosApi'
import type { ChartInterval } from '../api/stocksApi'
import type { Candle } from '../types'

export interface StockTradeMarker {
  date: string
  side: StockTrade['side']
  label: string
}

const BAR_DURATION: Partial<Record<ChartInterval, number>> = {
  '30m': 30 * 60_000,
  '1h': 60 * 60_000,
  '4h': 240 * 60_000,
}

function weekStart(date: string) {
  const day = new Date(date)
  return day.getTime() - ((day.getUTCDay() + 6) % 7) * 86_400_000
}

export function stockTradeMarkers(
  trades: StockTrade[],
  candles: Candle[],
  interval: ChartInterval,
  formingDate: string | undefined,
  label: (trades: StockTrade[]) => string,
): StockTradeMarker[] {
  if (!trades.length) return []

  const dates = new Set(candles.map(candle => candle.time))
  if (formingDate && interval === '1d') dates.add(formingDate)
  const weeks = new Map(interval === '1w' ? candles.map(candle => [weekStart(candle.time), candle.time]) : [])
  const duration = BAR_DURATION[interval]
  const starts = duration ? candles.map(candle => Date.parse(candle.time)) : []
  const tradesByBar = new Map<string, { date: string; trades: StockTrade[] }>()

  for (const trade of trades) {
    let date: string | undefined
    if (duration) {
      // Date-only trades have no known intraday candle.
      if (!trade.executedAt) continue
      const executed = Date.parse(trade.executedAt)
      let low = 0
      let high = starts.length
      while (low < high) {
        const middle = Math.floor((low + high) / 2)
        if (starts[middle] <= executed) low = middle + 1
        else high = middle
      }
      if (low && executed < starts[low - 1] + duration) date = candles[low - 1].time
    } else if (interval === '1w') {
      const week = weeks.get(weekStart(trade.date))
      if (week && trade.date <= week) date = week
    } else if (dates.has(trade.date)) {
      date = trade.date
    }
    if (!date) continue

    const key = `${date}:${trade.side}`
    const group = tradesByBar.get(key)
    if (group) group.trades.push(trade)
    else tradesByBar.set(key, { date, trades: [trade] })
  }

  return [...tradesByBar.values()].map(({ date, trades }) => ({
    date, side: trades[0].side, label: label(trades),
  }))
}
