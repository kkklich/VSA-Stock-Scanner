import { useEffect, useId, useRef, useState, type HTMLAttributes, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Instrument, Portfolio, PortfolioHeatmapHolding, PortfolioWalletSummary } from '../api/portfoliosApi'
import { useChartPalette } from '../lib/chartTheme'
import { currencyLabel, deltaTone } from '../lib/format'
import { canonicalTicker } from '../lib/markets'
import { heatmapColor, squarify } from '../lib/treemap'

const periodScales = { all: 60, '1y': 30, '3m': 20, '1m': 10, '1w': 10, '1d': 3 } as const
export type WalletHeatmapRange = keyof typeof periodScales
const periods = Object.keys(periodScales) as WalletHeatmapRange[]

interface PeriodControls {
  currency: string
  disabled: boolean
  period: WalletHeatmapRange
  periodStatus?: 'loading' | 'error'
  onPeriodChange: (period: WalletHeatmapRange) => void
}

interface HeatmapItem {
  id: string
  name: string
  subtitle: string
  labelDetails: (string | null | undefined)[]
  value: number | null
  stale: boolean
  partial?: boolean
  changes?: Pick<PortfolioWalletSummary, 'dayChange' | 'weekChange' | 'rangeChange'>
  to?: string
}

interface WalletProps extends PeriodControls {
  wallets: Portfolio[]
  valuations: PortfolioWalletSummary[]
  selected: string
  onSelect: (id: string) => void
}

export function PortfolioWalletHeatmap({
  wallets, valuations, ...props
}: WalletProps) {
  const byId = new Map(valuations.map(valuation => [valuation.walletId, valuation]))
  const items = wallets.map(wallet => {
    const changes = byId.get(wallet.id)
    const current = changes?.current
    const value = current?.value ?? null
    const labelDetails = [wallet.brokerAccountId, wallet.brokerAccountCurrency]
    return {
      id: wallet.id, name: wallet.name, labelDetails, value, changes,
      subtitle: [wallet.broker, ...labelDetails].filter(Boolean).join(' · '),
      partial: value != null && !!current && (current.missingQuotes > 0 || current.missingRates.length > 0),
      stale: !!current?.staleQuotes,
    }
  })
  return <PortfolioHeatmap {...props} items={items} />
}

export function PortfolioStockHeatmap({ walletName, holdings, instruments, ...props }: PeriodControls & {
  walletName: string; holdings: PortfolioHeatmapHolding[]; instruments: Instrument[]
}) {
  const instrumentNames = new Map(instruments.map(({ ticker, name }) => [canonicalTicker(ticker).toLowerCase(), name]))
  const items = holdings.map(holding => {
    const { ticker, currency, currentValue, staleQuote } = holding
    const labelDetails = [instrumentNames.get(canonicalTicker(ticker).toLowerCase()), currencyLabel(currency)]
    return {
      id: `${ticker}:${currency}`, name: ticker.toUpperCase(), labelDetails, value: currentValue,
      subtitle: labelDetails.filter(Boolean).join(' · '), stale: staleQuote, changes: holding,
      to: `/stock/${encodeURIComponent(ticker)}`,
    }
  })
  return <PortfolioHeatmap {...props} items={items} walletName={walletName} />
}

function HeatmapItemControl({ item, disabled, selected, onSelect, children, ...attributes }: {
  item: HeatmapItem; disabled: boolean; selected?: string; onSelect?: (id: string) => void; children: ReactNode
} & Pick<HTMLAttributes<HTMLElement>, 'className' | 'style' | 'tabIndex' | 'title' | 'aria-label'>) {
  return item.to ? <Link to={item.to} {...attributes}>{children}</Link>
    : <button type="button" disabled={disabled} aria-pressed={selected === item.id}
      onClick={() => onSelect?.(item.id)} {...attributes}>{children}</button>
}

function PortfolioHeatmap({ items, walletName, currency, selected, disabled, period, periodStatus,
  onSelect, onPeriodChange,
}: PeriodControls & { items: HeatmapItem[]; walletName?: string; selected?: string; onSelect?: (id: string) => void }) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const palette = useChartPalette()
  const chart = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const ranked = [...items].sort((a, b) =>
    (b.value ?? -Infinity) - (a.value ?? -Infinity) || a.name.localeCompare(b.name, i18n.language),
  )
  const valued = ranked.flatMap(entry => {
    const { value } = entry
    return value != null && value > 0 ? [{ ...entry, value }] : []
  })
  const hasTiles = valued.length > 0

  useEffect(() => {
    const node = chart.current
    if (!node) return
    const measure = () => setSize({ w: node.clientWidth, h: node.clientHeight })
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasTiles])

  const rects = squarify(valued.map(entry => entry.value), { x: 0, y: 0, ...size })
  const amountFormat = new Intl.NumberFormat(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const compactAmount = new Intl.NumberFormat(i18n.language, { notation: 'compact', maximumFractionDigits: 1 })
  const signedFormat = new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
  })
  const percentFormat = new Intl.NumberFormat(i18n.language, {
    style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
  })
  const dateFormat = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium', timeZone: 'UTC' })
  const unit = currencyLabel(currency)
  const unavailable = t('portfolio.overview.valueUnavailable')
  const changeKey = period === '1d' ? 'dayChange' : period === '1w' ? 'weekChange' : 'rangeChange'

  return <section aria-labelledby={id} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4 sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 id={id} className="text-lg font-semibold">{walletName
          ? t('portfolio.heatmap.stockTitle', { wallet: walletName }) : t('portfolio.heatmap.title')}</h2>
        <p className="mt-1 text-sm text-slate-400">{t(walletName ? 'portfolio.heatmap.stockDescription' : 'portfolio.heatmap.description', { currency: unit })}</p>
      </div>
      <div role="group" aria-label={t('portfolio.heatmap.period')} className="inline-flex flex-wrap rounded-lg border border-slate-700 p-0.5">
        {periods.map(option => <button key={option} type="button" aria-pressed={period === option} disabled={disabled}
          aria-label={t(`portfolio.overview.ranges.${option}.label`)} onClick={() => onPeriodChange(option)}
          className="rounded-md px-2.5 py-1 text-sm text-slate-400 aria-pressed:bg-slate-800 aria-pressed:text-slate-100 focus-visible:outline-2 focus-visible:outline-emerald-400">
          {option === 'all' ? 'Max' : t(`portfolio.overview.ranges.${option}.short`)}
        </button>)}
      </div>
    </div>
    {periodStatus && <p role={periodStatus === 'error' ? 'alert' : 'status'} className="text-sm text-slate-400">
      {t(periodStatus === 'loading' ? 'portfolio.heatmap.loading' : 'portfolio.heatmap.failed')}
    </p>}
    <div className={hasTiles ? 'grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]' : 'space-y-3'}>
      {hasTiles ? <div className="min-w-0 space-y-2">
        <div ref={chart} className="relative h-60 overflow-hidden rounded-lg bg-slate-950 sm:h-72">
          {valued.map((item, index) => {
            const { value } = item
            const rect = rects[index]
            if (rect.w < 1 || rect.h < 1) return null
            const percent = periodStatus ? null : item.changes?.[changeKey]?.percent
            const change = percent == null ? '—' : percentFormat.format(percent / 100)
            const color = percent == null ? palette.heatmapMissing : heatmapColor(percent / periodScales[period], palette)
            const label = [item.name, ...item.labelDetails,
              `${amountFormat.format(value)} ${unit}`, percent == null ? t('portfolio.heatmap.noPercent') : change,
            ].filter(Boolean).join(' · ')
            return <HeatmapItemControl key={item.id} item={item} tabIndex={-1} disabled={disabled} aria-label={label} title={label}
              selected={selected} onSelect={onSelect}
              className="absolute flex flex-col justify-center overflow-hidden border border-slate-950 text-left leading-tight text-white hover:brightness-110 aria-pressed:ring-2 aria-pressed:ring-inset aria-pressed:ring-white/70"
              style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h, backgroundColor: color }}>
              {rect.w >= 72 && rect.h >= 42 && <span className="flex min-w-0 flex-col gap-0.5 p-2 [text-shadow:0_1px_3px_rgb(0_0_0/0.6)]">
                <span className="truncate text-sm font-semibold">{item.name}</span>
                <span className="truncate text-xs font-medium tabular-nums">{change}</span>
                {rect.h >= 68 && <span className="truncate text-xs tabular-nums">
                  {(rect.w < 132 ? compactAmount : amountFormat).format(value)} {unit}
                </span>}
              </span>}
            </HeatmapItemControl>
          })}
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400">
          {[
            { key: 'decrease', color: heatmapColor(-1, palette) },
            { key: 'steady', color: heatmapColor(0, palette) },
            { key: 'increase', color: heatmapColor(1, palette) },
            { key: 'noPercent', color: palette.heatmapMissing },
          ].map(({ key, color }) => <li key={key} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ backgroundColor: color }} />{t(`portfolio.heatmap.${key}`)}
          </li>)}
        </ul>
      </div> : <p className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm text-slate-400">{t(walletName ? 'portfolio.heatmap.noStockTiles' : 'portfolio.heatmap.noTiles')}</p>}
      {ranked.length > 0 && <div className="min-w-0 rounded-lg border border-slate-800">
        <div aria-hidden="true" className="flex justify-between gap-2 border-b border-slate-800 px-3 py-2 text-xs text-slate-400">
          <span>{t(walletName ? 'portfolio.heatmap.stockValue' : 'portfolio.heatmap.walletValue')}</span><span>{t('portfolio.heatmap.change')}</span>
        </div>
        <ul className="divide-y divide-slate-800 lg:max-h-64 lg:overflow-y-auto">
          {ranked.map(item => {
            const change = periodStatus ? null : item.changes?.[changeKey]
            const value = item.value == null ? unavailable : `${amountFormat.format(item.value)} ${unit}`
            const percent = change?.percent == null ? null : percentFormat.format(change.percent / 100)
            return <li key={item.id}>
              <HeatmapItemControl item={item} disabled={disabled} selected={selected} onSelect={onSelect}
                className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-800/60 aria-pressed:bg-slate-800/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-emerald-400">
                <span className="min-w-0">
                  <span className="block break-words font-medium">{item.name}</span>
                  <span className="block break-words text-xs text-slate-500">{item.subtitle}</span>
                  <span className="block break-words text-xs tabular-nums text-slate-400">{value}</span>
                  {item.partial && <span className="block text-xs text-amber-400">{t('portfolio.overview.partial')}</span>}
                  {item.stale && <span className="block text-xs text-amber-400">{t('portfolio.heatmap.staleQuotes')}</span>}
                </span>
                <span className="min-w-0 text-right">
                  {change ? <>
                    <span className={`block break-words font-medium tabular-nums ${deltaTone(change.amount)}`}>{percent ?? '—'}</span>
                    <span className="block break-words text-xs tabular-nums text-slate-400">{signedFormat.format(change.amount)} {unit}</span>
                    <span className="block text-xs text-slate-400">{t('portfolio.overview.since', { date: dateFormat.format(new Date(change.since)) })}</span>
                    {change.partial && <span className="block text-xs text-amber-400">{t('portfolio.heatmap.partialChange')}</span>}
                  </> : <span className="text-xs text-slate-400">{periodStatus ? '—' : t('portfolio.overview.changeUnavailable')}</span>}
                </span>
              </HeatmapItemControl>
            </li>
          })}
        </ul>
      </div>}
    </div>
  </section>
}
