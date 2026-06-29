// Small reusable presentational pieces used across pages.

import type { SignalVerdict } from '../types'
import { ratingTone } from '../lib/format'

/** Rounded panel/card container matching the dashboard surface. */
export function Card({
  className = '',
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      className={
        'rounded-xl border border-slate-800 bg-slate-900/60 ' + className
      }
    >
      {children}
    </div>
  )
}

/** A small caps section heading used inside cards. */
export function CardTitle({
  children,
  right,
}: {
  children: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between px-4 pt-3 pb-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
        {children}
      </h3>
      {right}
    </div>
  )
}

/** VSA rating: numeric value + thin progress bar. */
export function RatingMeter({ rating }: { rating: number }) {
  const tone = ratingTone(rating)
  return (
    <div className="flex items-center gap-3">
      <span className={'w-7 text-sm font-semibold tabular-nums ' + tone.text}>
        {rating}
      </span>
      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-700/60">
        <div
          className={'h-full rounded-full ' + tone.bar}
          style={{ width: `${rating}%` }}
        />
      </div>
    </div>
  )
}

const verdictStyles: Record<SignalVerdict, string> = {
  'Strong Buy': 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
  Buy: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/20',
  Hold: 'bg-slate-600/30 text-slate-300 ring-slate-500/30',
  Sell: 'bg-rose-500/10 text-rose-300 ring-rose-500/20',
  'Strong Sell': 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
}

/** Colored verdict badge (Strong Buy / Buy / Hold / ...). */
export function SignalBadge({ verdict }: { verdict: SignalVerdict }) {
  return (
    <span
      className={
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ' +
        verdictStyles[verdict]
      }
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {verdict}
    </span>
  )
}

/** Tiny inline SVG sparkline; colored by net direction. */
export function Sparkline({
  data,
  width = 72,
  height = 24,
}: {
  data: number[]
  width?: number
  height?: number
}) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const stepX = width / (data.length - 1)
  const points = data
    .map((v, i) => {
      const x = i * stepX
      const y = height - ((v - min) / span) * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const up = data[data.length - 1] >= data[0]
  const stroke = up ? '#10B981' : '#F43F5E'
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
