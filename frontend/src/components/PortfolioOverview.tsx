import { useEffect, useId, useRef, useState } from 'react'
import { AreaSeries, ColorType, createChart, isBusinessDay, type AreaData, type Time } from 'lightweight-charts'
import { useTranslation } from 'react-i18next'
import type { PortfolioSummary } from '../api/portfoliosApi'
import { useChartPalette } from '../lib/chartTheme'
import { currencyLabel, deltaTone } from '../lib/format'

const unavailable = '—'

function formatAmount(amount: number, locale: string, signed = false) {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: signed ? 'exceptZero' : 'auto',
  }).format(amount)
}

function money(amount: number, currency: string, locale: string, signed = false) {
  return `${formatAmount(amount, locale, signed)} ${currencyLabel(currency)}`
}

function formatDate(date: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric', month: 'short', timeZone: 'UTC',
  }).format(new Date(date))
}

function dateFromChartTime(time: Time) {
  if (isBusinessDay(time)) return new Date(Date.UTC(time.year, time.month - 1, time.day)).toISOString().slice(0, 10)
  return typeof time === 'string' ? time : new Date(time * 1000).toISOString().slice(0, 10)
}

function ValueChange({ change, label, currency }: {
  change: PortfolioSummary['dayChange']; label: string; currency: string
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n.language
  const percent = change?.percent == null ? null : new Intl.NumberFormat(locale, {
    style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
  }).format(change.percent / 100)
  return <div className="min-w-0">
    <dt className="text-sm text-slate-400">{label}</dt>
    <dd className={`mt-1 flex flex-wrap items-baseline gap-x-2 text-lg font-semibold tabular-nums ${deltaTone(change?.amount ?? 0)}`}>
      <span className="min-w-0 break-words">{change ? money(change.amount, currency, locale, true) : unavailable}</span>
      {percent && <span className="text-sm font-medium">({percent})</span>}
    </dd>
    <dd className="mt-1 text-xs text-slate-400">{change
      ? t('portfolio.overview.since', { date: formatDate(change.since, locale) })
      : t('portfolio.overview.changeUnavailable')}</dd>
  </div>
}

function ValueHistory({ history, currency }: { history: PortfolioSummary['history']; currency: string }) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const locale = i18n.language
  const palette = useChartPalette()
  const container = useRef<HTMLDivElement>(null)
  const [hoverDate, setHoverDate] = useState<string>()
  const focused = history.find(point => point.date === hoverDate) ?? history[history.length - 1]
  const pricedDays = history.filter(point => point.value !== null).length
  const canPlot = pricedDays >= 2

  useEffect(() => {
    if (!canPlot || !container.current) return
    const dateLabel = (time: Time) => formatDate(dateFromChartTime(time), locale)
    const chart = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: palette.axisText,
        fontFamily: 'inherit',
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: palette.scaleBorder },
      },
      localization: { locale, timeFormatter: dateLabel },
      timeScale: { borderColor: palette.scaleBorder, tickMarkFormatter: dateLabel },
      rightPriceScale: { borderColor: palette.scaleBorder, scaleMargins: { top: 0.12, bottom: 0.15 } },
      handleScroll: false,
      handleScale: false,
    })

    // Each uninterrupted run has its own series so the chart shows gaps on days
    // when the combined value could not be calculated.
    const segments: AreaData[][] = []
    let segment: AreaData[] | undefined
    for (const { date, value } of history) {
      if (value === null) {
        segment = undefined
        continue
      }
      if (!segment) {
        segment = []
        segments.push(segment)
      }
      segment.push({ time: date, value })
    }
    const axisValue = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 })
    for (const [index, points] of segments.entries()) {
      const series = chart.addSeries(AreaSeries, {
        lineColor: palette.bull,
        topColor: `${palette.bull}32`,
        bottomColor: `${palette.bull}03`,
        lineWidth: 2,
        pointMarkersVisible: true,
        pointMarkersRadius: 3,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat: { type: 'custom', formatter: (value: number) => axisValue.format(value), minMove: 0.01 },
      })
      series.setData(index === 0
        ? history.map(point => points.find(item => item.time === point.date) ?? { time: point.date })
        : points)
    }
    chart.timeScale().fitContent()
    chart.subscribeCrosshairMove(({ time }) => setHoverDate(time === undefined ? undefined : dateFromChartTime(time)))
    return () => chart.remove()
  }, [canPlot, history, locale, palette])

  return <figure aria-labelledby={id} className="min-w-0 border-t border-slate-800 pt-4">
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <figcaption id={id} className="text-sm font-semibold text-slate-200">
        {t('portfolio.overview.chartTitle', { currency: currencyLabel(currency) })}
      </figcaption>
      {canPlot && focused && <p aria-hidden="true" className="text-sm text-slate-400 tabular-nums">
        {formatDate(focused.date, locale)}
        <span className="ml-2 font-medium text-slate-200">
          {focused.value === null ? unavailable : money(focused.value, currency, locale)}
        </span>
      </p>}
    </div>
    {canPlot
      ? <div ref={container} aria-hidden="true" className="h-52 w-full sm:h-60" />
      : <p className="rounded-lg bg-slate-950 p-4 text-sm text-slate-400">{t('portfolio.overview.historyUnavailable')}</p>}
    {pricedDays > 0 && <details className="mt-3 text-sm text-slate-400">
      <summary className="w-fit cursor-pointer rounded hover:text-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-400">
        {t('portfolio.overview.chartValues')}
      </summary>
      <table className="mt-2 w-full max-w-sm table-fixed border-collapse text-left tabular-nums">
        <thead><tr className="text-xs"><th scope="col" className="py-1 font-medium">{t('portfolio.overview.valuationDate')}</th>
          <th scope="col" className="py-1 text-right font-medium">{t('portfolio.overview.value')}</th></tr></thead>
        <tbody>{history.map(point => <tr key={point.date} className="border-t border-slate-800">
          <th scope="row" className="py-1 font-normal">{formatDate(point.date, locale)}</th>
          <td className="py-1 text-right">{point.value === null
            ? t('portfolio.overview.valueUnavailable')
            : money(point.value, currency, locale)}</td>
        </tr>)}</tbody>
      </table>
    </details>}
  </figure>
}

export function PortfolioOverview({ summary, walletCount, hasMultipleXtbWallets, staleSince }: {
  summary: PortfolioSummary; walletCount: number; hasMultipleXtbWallets?: boolean; staleSince?: string
}) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const locale = i18n.language
  const { currency, current, currencyTotals } = summary
  const showBreakdown = currencyTotals.length > 1 || currencyTotals.some(total => total.currency !== currency)
  return <section aria-labelledby={id} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4 sm:p-5">
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2 id={id} className="text-lg font-semibold">{t('portfolio.overview.title')}</h2>
      {walletCount > 0 && <p className="text-sm text-slate-400">{t('portfolio.overview.wallets', { count: walletCount })}</p>}
    </div>
    {walletCount === 0 ? <p className="text-sm text-slate-400">{t('portfolio.overview.empty')}</p> : <>
      {staleSince && <p role="status" className="text-sm text-amber-400">{t('portfolio.overview.staleSnapshot', {
        timestamp: new Date(staleSince).toLocaleString(locale, {
          dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Warsaw',
        }),
      })}</p>}
      <dl className="grid grid-cols-2 items-start gap-y-4 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] sm:divide-x sm:divide-slate-800 sm:[&>div+div]:pl-4">
        <div className="col-span-2 min-w-0 sm:col-span-1">
          <dt className="text-sm text-slate-400">{t('portfolio.overview.value')}</dt>
          <dd className="mt-0.5 break-words text-2xl font-semibold tracking-tight text-slate-100 tabular-nums sm:text-3xl">
            {current.value === null ? unavailable : money(current.value, currency, locale)}
          </dd>
        </div>
        <ValueChange change={summary.dayChange} label={t('portfolio.overview.dayChange')} currency={currency} />
        <ValueChange change={summary.weekChange} label={t('portfolio.overview.weekChange')} currency={currency} />
      </dl>
      {hasMultipleXtbWallets && <p className="text-sm text-amber-400">{t('portfolio.overview.xtbOverlap')}</p>}
      {(current.value === null || current.staleQuotes > 0) && <div className="rounded-lg border border-amber-400/25 bg-amber-400/5 px-3 py-2 text-sm text-amber-400">
        {current.value === null && <p className="font-medium">{t('portfolio.overview.totalUnavailable')}</p>}
        {current.missingQuotes > 0 && <p>{t('portfolio.overview.missingQuotes', { count: current.missingQuotes })}</p>}
        {current.missingRates.length > 0 && <p>{t('portfolio.overview.missingRates', {
          currencies: current.missingRates.map(currencyLabel).join(', '),
        })}</p>}
        {current.staleQuotes > 0 && <p>{t('portfolio.overview.staleQuotes', { count: current.staleQuotes })}</p>}
      </div>}
      {showBreakdown && <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 rounded-lg bg-slate-950/60 px-3 py-2">
        <p className="text-xs font-medium text-slate-400">{t('portfolio.overview.currencyBreakdown')}</p>
        <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm tabular-nums">{currencyTotals.map(total => <div key={total.currency} className="flex gap-1.5">
          <dt className="text-slate-400">{currencyLabel(total.currency)}</dt>
          <dd className="font-medium text-slate-200">{total.marketValue === null
            ? t('portfolio.overview.valueUnavailable')
            : formatAmount(total.marketValue, locale)}</dd>
        </div>)}</dl>
      </div>}
      <ValueHistory history={summary.history} currency={currency} />
      <p className="text-xs leading-relaxed text-slate-400">{t('portfolio.overview.method')}</p>
    </>}
  </section>
}
