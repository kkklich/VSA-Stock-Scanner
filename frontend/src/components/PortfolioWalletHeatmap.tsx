import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Portfolio, PortfolioWalletSummary } from '../api/portfoliosApi'
import { useChartPalette } from '../lib/chartTheme'
import { currencyLabel, deltaTone } from '../lib/format'
import { heatmapColor, squarify } from '../lib/treemap'

const periods = [
  { key: 'dayChange', scale: 3 },
  { key: 'weekChange', scale: 10 },
] as const

interface Props {
  wallets: Portfolio[]
  valuations: PortfolioWalletSummary[]
  currency: string
  selected: string
  disabled: boolean
  onSelect: (id: string) => void
}

export function PortfolioWalletHeatmap({ wallets, valuations, currency, selected, disabled, onSelect }: Props) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const palette = useChartPalette()
  const [period, setPeriod] = useState<(typeof periods)[number]>(periods[1])
  const chart = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const byId = new Map(valuations.map(valuation => [valuation.walletId, valuation]))
  const ranked = wallets.map(wallet => ({ wallet, valuation: byId.get(wallet.id) })).sort((a, b) =>
    (b.valuation?.current.value ?? -Infinity) - (a.valuation?.current.value ?? -Infinity)
    || a.wallet.name.localeCompare(b.wallet.name, i18n.language),
  )
  const valued = ranked.flatMap(entry => {
    const value = entry.valuation?.current.value
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
  const signedFormat = new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
  })
  const percentFormat = new Intl.NumberFormat(i18n.language, {
    style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
  })
  const unit = currencyLabel(currency)
  const unavailable = t('portfolio.overview.valueUnavailable')

  return <section aria-labelledby={id} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4 sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 id={id} className="text-lg font-semibold">{t('portfolio.heatmap.title')}</h2>
        <p className="mt-1 text-sm text-slate-400">{t('portfolio.heatmap.description', { currency: unit })}</p>
      </div>
      <div role="group" aria-label={t('portfolio.heatmap.period')} className="inline-flex rounded-lg border border-slate-700 p-0.5">
        {periods.map(option => <button key={option.key} type="button" aria-pressed={period === option}
          onClick={() => setPeriod(option)} className="rounded-md px-3 py-1 text-sm text-slate-400 aria-pressed:bg-slate-800 aria-pressed:text-slate-100 focus-visible:outline-2 focus-visible:outline-emerald-400">
          {t(`portfolio.heatmap.${option.key}`)}
        </button>)}
      </div>
    </div>
    <div className={hasTiles ? 'grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]' : 'space-y-3'}>
      {hasTiles ? <div className="min-w-0 space-y-2">
        <div ref={chart} className="relative h-60 overflow-hidden rounded-lg bg-slate-950 sm:h-72">
          {valued.map(({ wallet, valuation, value }, index) => {
            const rect = rects[index]
            if (rect.w < 1 || rect.h < 1) return null
            const percent = valuation?.[period.key]?.percent
            const change = percent == null ? '—' : percentFormat.format(percent / 100)
            const color = percent == null ? palette.heatmapMissing : heatmapColor(percent / period.scale, palette)
            const label = [wallet.name, wallet.brokerAccountId, wallet.brokerAccountCurrency,
              `${amountFormat.format(value)} ${unit}`, percent == null ? t('portfolio.heatmap.noPercent') : change,
            ].filter(Boolean).join(' · ')
            return <button key={wallet.id} type="button" tabIndex={-1} disabled={disabled} aria-label={label} title={label}
              aria-pressed={selected === wallet.id} onClick={() => onSelect(wallet.id)}
              className="absolute overflow-hidden border border-slate-950 text-left leading-tight text-white enabled:hover:brightness-110 aria-pressed:ring-2 aria-pressed:ring-inset aria-pressed:ring-white/70"
              style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h, backgroundColor: color }}>
              {rect.w >= 72 && rect.h >= 42 && <span className="flex min-w-0 flex-col gap-1 p-2 [text-shadow:0_1px_3px_rgb(0_0_0/0.6)] sm:p-3">
                <span className="truncate text-sm font-semibold">{wallet.name}</span>
                <span className="text-xs font-medium tabular-nums">{change}</span>
              </span>}
            </button>
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
      </div> : <p className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm text-slate-400">{t('portfolio.heatmap.noTiles')}</p>}
      <div className="min-w-0 rounded-lg border border-slate-800">
        <div aria-hidden="true" className="flex justify-between gap-2 border-b border-slate-800 px-3 py-2 text-xs text-slate-400">
          <span>{t('portfolio.heatmap.walletValue')}</span><span>{t('portfolio.heatmap.change')}</span>
        </div>
        <ul className="divide-y divide-slate-800 lg:max-h-64 lg:overflow-y-auto">
          {ranked.map(({ wallet, valuation }) => {
            const current = valuation?.current
            const change = valuation?.[period.key]
            const value = current?.value == null ? unavailable : `${amountFormat.format(current.value)} ${unit}`
            const partial = current?.value != null && (current.missingQuotes > 0 || current.missingRates.length > 0)
            const percent = change?.percent == null ? null : percentFormat.format(change.percent / 100)
            return <li key={wallet.id}>
              <button type="button" disabled={disabled} aria-pressed={selected === wallet.id} onClick={() => onSelect(wallet.id)}
                className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-sm enabled:hover:bg-slate-800/60 aria-pressed:bg-slate-800/70 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-emerald-400">
                <span className="min-w-0">
                  <span className="block break-words font-medium">{wallet.name}</span>
                  <span className="block break-words text-xs text-slate-500">
                    {[wallet.broker, wallet.brokerAccountId, wallet.brokerAccountCurrency].filter(Boolean).join(' · ')}
                  </span>
                  <span className="block break-words text-xs tabular-nums text-slate-400">{value}</span>
                  {partial && <span className="block text-xs text-amber-400">{t('portfolio.overview.partial')}</span>}
                  {!!current?.staleQuotes && <span className="block text-xs text-amber-400">{t('portfolio.heatmap.staleQuotes')}</span>}
                </span>
                <span className="min-w-0 text-right">
                  {change ? <>
                    <span className={`block break-words font-medium tabular-nums ${deltaTone(change.amount)}`}>{percent ?? '—'}</span>
                    <span className="block break-words text-xs tabular-nums text-slate-400">{signedFormat.format(change.amount)} {unit}</span>
                    {change.partial && <span className="block text-xs text-amber-400">{t('portfolio.heatmap.partialChange')}</span>}
                  </> : <span className="text-xs text-slate-400">{t('portfolio.overview.changeUnavailable')}</span>}
                </span>
              </button>
            </li>
          })}
        </ul>
      </div>
    </div>
  </section>
}
