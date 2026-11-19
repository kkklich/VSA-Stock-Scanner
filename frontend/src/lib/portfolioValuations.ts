import type { Portfolio, PortfolioTotal, Position } from '../api/portfoliosApi'

function addMarketValues(left: number | null, right: number | null) {
  return left === null || right === null ? null : left + right
}

function unrealizedValue({ marketValue, cost }: Pick<PortfolioTotal, 'marketValue' | 'cost'>) {
  const unrealizedPnl = marketValue === null ? null : marketValue - cost
  const unrealizedPnlPct = unrealizedPnl === null || cost === 0 ? null : unrealizedPnl / cost * 100
  return { unrealizedPnl, unrealizedPnlPct }
}

export function groupWalletValuations(wallets: Portfolio[]) {
  const grouped = new Map<string, Position>()
  for (const wallet of wallets) {
    for (const position of wallet.positions) {
      const key = `${position.ticker}:${position.currency}`
      const group = grouped.get(key)
      if (!group) {
        grouped.set(key, { ...position })
        continue
      }

      // All wallets in a snapshot use the same quote for a given ticker and currency.
      group.quantity += position.quantity
      group.cost += position.cost
      group.marketValue = addMarketValues(group.marketValue, position.marketValue)
      group.realizedPnl += position.realizedPnl
    }
  }

  const byCurrency = new Map<string, Omit<PortfolioTotal, 'unrealizedPnl' | 'unrealizedPnlPct'>>()
  const positions = Array.from(grouped.values(), position => {
    const { currency, quantity, cost, marketValue, realizedPnl } = position
    const total = byCurrency.get(currency) ?? { currency, cost: 0, marketValue: null, realizedPnl: 0, missingQuotes: 0 }
    total.realizedPnl += realizedPnl
    if (marketValue === null) {
      total.missingQuotes++
    } else if (quantity) {
      total.cost += cost
      total.marketValue = (total.marketValue ?? 0) + marketValue
    }
    byCurrency.set(currency, total)
    return { ...position, averagePrice: quantity ? cost / quantity : null, ...unrealizedValue(position) }
  })

  const totals = Array.from(byCurrency.values(), total => {
    if (total.marketValue === null && !total.missingQuotes) total.marketValue = 0
    return { ...total, ...unrealizedValue(total) }
  })
  return { positions, totals }
}
