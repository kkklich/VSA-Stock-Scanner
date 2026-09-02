// Analytics Summary card (stock detail page) — the consolidated "bottom line".
// The backend fuses the app's separate per-stock opinions (VSA verdict, AI
// Insight second opinion, Signal Trust Score and every trading method) into one
// stance, an agreement score and a plain-language reconciliation. Computed
// locally by app/analysis/analytics_summary.py; no external AI services.

import { useTranslation } from 'react-i18next'
import { Loader2, Scale } from 'lucide-react'
import { Card, CardTitle, InfoTip } from './ui'
import { useOpinionSummary } from '../hooks/useOpinionSummary'
import type {
  ApiOpinionSource,
  OpinionStance,
} from '../api/stocksApi'

/** Badge + meter colouring per consolidated stance (label is translated). */
const STANCE_STYLE: Record<
  OpinionStance,
  { badge: string; text: string; bar: string }
> = {
  bullish: {
    badge: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
    text: 'text-emerald-400',
    bar: 'bg-emerald-500/70',
  },
  bearish: {
    badge: 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
    text: 'text-rose-400',
    bar: 'bg-rose-500/70',
  },
  neutral: {
    badge: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
    text: 'text-slate-300',
    bar: 'bg-slate-500/70',
  },
  mixed: {
    badge: 'bg-amber-500/15 text-amber-400 ring-amber-500/30',
    text: 'text-amber-400',
    bar: 'bg-amber-500/70',
  },
}

/** Dot colour per source stance (green = bullish/reliable, rose = bearish/unreliable). */
const DOT: Record<ApiOpinionSource['stance'], string> = {
  bullish: 'bg-emerald-500',
  bearish: 'bg-rose-500',
  neutral: 'bg-slate-500',
  unavailable: 'bg-slate-700',
}

function SourceRow({ s }: { s: ApiOpinionSource }) {
  const { t } = useTranslation()
  return (
    <li className="flex items-center justify-between gap-2 py-1.5" title={s.detail}>
      <span className="flex min-w-0 items-center gap-2">
        <span className={'h-2 w-2 shrink-0 rounded-full ' + DOT[s.stance]} />
        <span className="truncate text-xs text-slate-300">{s.label}</span>
        {s.firedRecently && (
          <span className="shrink-0 rounded bg-emerald-500/15 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-emerald-400">
            {t('chart.summary.fired')}
          </span>
        )}
      </span>
      <span
        className={
          'shrink-0 text-xs tabular-nums ' +
          (s.stance === 'unavailable' ? 'text-slate-600' : 'text-slate-400')
        }
      >
        {s.headline}
      </span>
    </li>
  )
}

export function AnalyticsSummaryCard({ ticker }: { ticker: string }) {
  const { t } = useTranslation()
  const { data, loading, error } = useOpinionSummary(ticker)

  const style = data ? STANCE_STYLE[data.stance] : STANCE_STYLE.neutral
  const directionSources = data?.sources.filter((s) => s.kind === 'direction') ?? []
  const reliabilitySources = data?.sources.filter((s) => s.kind === 'reliability') ?? []

  return (
    <Card>
      <CardTitle>
        <span className="inline-flex items-center gap-1.5">
          <Scale size={14} className="text-emerald-400" /> {t('chart.summary.title')}
        </span>{' '}
        <InfoTip text={t('chart.summary.info')} />
      </CardTitle>

      <div className="px-4 pb-4">
        {loading && !data && (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <Loader2 size={14} className="animate-spin" /> {t('chart.summary.loading')}
          </div>
        )}

        {error && !data && (
          <p className="py-2 text-xs text-slate-500">
            {t('chart.summary.unavailable', { error })}
          </p>
        )}

        {data && (
          <>
            <div className="flex items-center gap-3">
              <span
                className={
                  'rounded-md px-2.5 py-1 text-sm font-semibold ring-1 ring-inset ' +
                  style.badge
                }
              >
                {t('chart.summary.stance.' + data.stance)}
              </span>
              <div className="flex-1">
                <div className="mb-1 flex justify-between text-xs text-slate-500">
                  <span>{t('chart.summary.agreement')}</span>
                  <span className="tabular-nums text-slate-300">{data.agreement}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-800">
                  <div
                    className={'h-1.5 rounded-full ' + style.bar}
                    style={{ width: `${data.agreement}%` }}
                  />
                </div>
              </div>
            </div>

            <p className={'mt-3 text-sm font-medium leading-snug ' + style.text}>
              {data.headline}
            </p>

            <p className="mt-2 text-xs leading-relaxed text-slate-400">{data.summary}</p>

            {directionSources.length > 0 && (
              <ul className="mt-3 border-t border-slate-800 pt-2">
                {directionSources.map((s) => (
                  <SourceRow key={s.key} s={s} />
                ))}
              </ul>
            )}

            {reliabilitySources.length > 0 && (
              <ul className="mt-1 border-t border-slate-800/60 pt-2">
                {reliabilitySources.map((s) => (
                  <SourceRow key={s.key} s={s} />
                ))}
              </ul>
            )}

            <p className="mt-3 text-[10px] text-slate-600">
              {t('chart.summary.disclaimer', {
                engine: data.engine,
                asOf: data.asOf,
              })}
            </p>
          </>
        )}
      </div>
    </Card>
  )
}
