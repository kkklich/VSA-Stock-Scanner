// "Volume (RVOL)" card for the stock-detail page — the single-stock form of the
// /volume-surge screen. Shows this stock's multi-day relative volume (the last
// few sessions' average volume vs its own recent baseline), so the user can see
// whether it is trading on unusual volume right now without leaving the page.
// Data comes from GET /api/stocks/{ticker}/volume (shares the same maths as the
// scanner), fetched independently of the chart range.

import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import type { ApiTickerVolume } from '../api/stocksApi'
import { Card, CardTitle, InfoTip } from './ui'
import { deltaTone, fmtCompactPln, fmtPct } from '../lib/format'

/** Attention colour for the RVOL badge: the higher the ratio, the hotter. */
function ratioTone(ratio: number): string {
  if (ratio >= 3) return 'bg-amber-500/15 text-amber-400 ring-amber-500/30'
  if (ratio >= 1.5) return 'bg-amber-500/10 text-amber-300 ring-amber-500/20'
  return 'bg-slate-600/30 text-slate-300 ring-slate-500/30'
}

/** Shares in compact form ("1.2 M", "320 K"); reuses the compact PLN helper. */
const fmtShares = (n: number): string => fmtCompactPln(n)

export function VolumeCard({
  data,
  loading,
}: {
  data: ApiTickerVolume | null
  loading: boolean
}) {
  const { t } = useTranslation()

  const ready =
    data != null && data.available && data.volumeRatio != null

  return (
    <Card>
      <CardTitle>
        {t('chart.volume.title')} <InfoTip text={t('chart.volume.info')} />
      </CardTitle>
      <div className="px-4 pb-4">
        {loading && !data ? (
          <div className="flex items-center gap-2 py-2 text-slate-500">
            <Loader2 size={14} className="animate-spin" /> {t('common.loading')}
          </div>
        ) : !ready ? (
          <p className="py-2 text-sm text-slate-500">{t('chart.volume.noData')}</p>
        ) : (
          <>
            <div className="flex items-end gap-2">
              <span
                className={
                  'rounded-md px-2 py-1 text-3xl font-bold tabular-nums ring-1 ring-inset ' +
                  ratioTone(data.volumeRatio!)
                }
              >
                {data.volumeRatio!.toFixed(1)}×
              </span>
              <span className="mb-1 text-xs text-slate-500">
                {t('chart.volume.relativeVolume')}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {t('chart.volume.window', {
                recent: data.recentDays,
                baseline: data.baselineDays,
              })}
            </p>

            <dl className="mt-3 space-y-2 text-sm">
              <Row
                label={t('chart.volume.recentAvg', { count: data.recentDays })}
                value={
                  data.recentAvgVolume != null
                    ? fmtShares(data.recentAvgVolume)
                    : '—'
                }
              />
              <Row
                label={t('chart.volume.baselineAvg', { count: data.baselineDays })}
                value={
                  data.baselineAvgVolume != null
                    ? fmtShares(data.baselineAvgVolume)
                    : '—'
                }
              />
              <Row
                label={t('chart.volume.lastSession')}
                value={data.lastVolume != null ? fmtShares(data.lastVolume) : '—'}
              />
              <Row
                label={t('chart.volume.lastDayRvol')}
                value={
                  data.lastDayRatio != null ? `${data.lastDayRatio.toFixed(1)}×` : '—'
                }
              />
              <Row
                label={t('chart.volume.daysAbove')}
                value={
                  data.daysAboveBaseline != null
                    ? `${data.daysAboveBaseline}/${data.recentDays}`
                    : '—'
                }
              />
              <Row
                label={t('chart.volume.priceMove')}
                value={
                  data.priceChangePct != null ? (
                    <span className={'tabular-nums ' + deltaTone(data.priceChangePct)}>
                      {fmtPct(data.priceChangePct)}
                    </span>
                  ) : (
                    '—'
                  )
                }
              />
            </dl>
          </>
        )}
      </div>
    </Card>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-200">{value}</dd>
    </div>
  )
}
