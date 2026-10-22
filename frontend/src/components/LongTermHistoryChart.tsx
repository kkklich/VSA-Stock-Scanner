import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { LongTermSnapshot } from '../types/longTerm'
import { scoreText } from '../lib/longTerm'

const WIDTH = 640
const HEIGHT = 220
const LEFT = 34
const RIGHT = 12
const TOP = 14
const BOTTOM = 16

function observationTime(value: string): number {
  // Require a real, timezone-qualified ISO date. Date.parse alone normalises
  // impossible dates such as February 30 and accepts ambiguous local dates.
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/.exec(value)
  if (!parts) return NaN
  const [, year, month, day, hour, minute, second, fraction = '0', zone] = parts
  const daysInMonth = new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate()
  if (Number(month) < 1 || Number(month) > 12 || Number(day) < 1 || Number(day) > daysInMonth
    || Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59) return NaN
  // The archive may carry microseconds. Do not collapse distinct revisions by
  // letting Date.parse truncate every fractional timestamp to milliseconds.
  return Date.parse(`${year}-${month}-${day}T${hour}:${minute}:${second}${zone}`) + Number(`0.${fraction}`) * 1000
}

/** Plot acquisition time, retaining revisions and gaps rather than resampling by day. */
export function LongTermHistoryChart({ items }: { items: LongTermSnapshot[] }) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const observations = items.map((item, index) => ({ item, index, time: observationTime(item.recordedAt) }))
    .filter(({ time }) => Number.isFinite(time))
    .sort((a, b) => a.time - b.time || a.index - b.index)
  const usable = observations.filter(({ item }) => item.score !== null && Number.isFinite(item.score) && item.score >= 0 && item.score <= 100)
  const distinctTimes = new Set(usable.map(({ time }) => time))
  if (distinctTimes.size < 2) return <p className="rounded-lg bg-slate-800/50 p-3 text-sm text-slate-400">{t('longTerm.chart.insufficient')}</p>

  // Include dated missing scores in the time domain; they are breaks, never zeroes.
  const firstTime = observations[0].time
  const lastTime = observations[observations.length - 1].time
  const x = (time: number) => LEFT + ((time - firstTime) / (lastTime - firstTime)) * (WIDTH - LEFT - RIGHT)
  const y = (score: number) => TOP + ((100 - score) / 100) * (HEIGHT - TOP - BOTTOM)
  const models = [...new Set(usable.map(({ item }) => item.modelVersion))]
  const segments: { model: string; points: string[] }[] = []
  let current: typeof segments[number] | null = null
  for (const { item, time } of observations) {
    if (item.score === null || !Number.isFinite(item.score) || item.score < 0 || item.score > 100) {
      current = null
      continue
    }
    if (!current || current.model !== item.modelVersion) {
      current = { model: item.modelVersion, points: [] }
      segments.push(current)
    }
    current.points.push(`${x(time)},${y(item.score)}`)
  }
  const dateLabel = (time: number) => new Date(time).toLocaleString(i18n.language, { dateStyle: 'short', timeStyle: 'medium' })

  return <figure className="min-w-0 space-y-3 rounded-lg border border-slate-800 p-3">
    <figcaption id={`${id}-title`} className="text-sm font-semibold text-slate-200">{t('longTerm.chart.title')}</figcaption>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} className="block h-auto w-full overflow-visible">
      {[0, 50, 100].map((value) => <g key={value}>
        <line x1={LEFT} x2={WIDTH - RIGHT} y1={y(value)} y2={y(value)} className="stroke-slate-700" strokeDasharray="3 5" />
        <text x={LEFT - 8} y={y(value)} textAnchor="end" dominantBaseline="middle" className="fill-slate-400 text-xs">{value}</text>
      </g>)}
      {segments.filter(({ points }) => points.length > 1).map(({ model, points }, index) => <polyline
        key={index} data-model={model} points={points.join(' ')} fill="none" className="stroke-sky-400" strokeWidth="2" vectorEffect="non-scaling-stroke"
      />)}
      {usable.map(({ item, time, index }) => <circle key={index} cx={x(time)} cy={y(item.score!)} r="3.5" className="fill-sky-400 stroke-slate-900" strokeWidth="1.5" data-recorded-at={item.recordedAt} data-score={item.score} data-model={item.modelVersion}>
        <title>{`${t('longTerm.recordedAt')}: ${dateLabel(time)} (${item.recordedAt}) · ${t('longTerm.score')}: ${scoreText(item.score, i18n.language)} · ${t('longTerm.modelVersion')}: ${item.modelVersion} · ${t('longTerm.session')}: ${item.asOf ?? '—'}`}</title>
      </circle>)}
    </svg>
    <div aria-hidden="true" className="flex justify-between gap-4 text-xs tabular-nums text-slate-400"><span>{dateLabel(firstTime)}</span><span className="text-right">{dateLabel(lastTime)}</span></div>
    <p id={`${id}-description`} className="text-xs leading-relaxed text-slate-400">{t('longTerm.chart.description')}</p>
    <p className="text-xs text-slate-400">{t('longTerm.chart.models', { models: models.join(', ') })}</p>
    {distinctTimes.size < usable.length && <p className="text-xs text-slate-400">{t('longTerm.chart.overlapping')}</p>}
    {observations.length < items.length && <p className="text-xs text-slate-400">{t('longTerm.chart.invalidDates')}</p>}
  </figure>
}
