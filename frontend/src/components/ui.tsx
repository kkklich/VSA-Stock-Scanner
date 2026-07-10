// Small reusable presentational pieces used across pages.

import { useState } from 'react'
import { ArrowDown, ArrowDownUp, ArrowUp, Info } from 'lucide-react'
import type { SignalVerdict } from '../types'
import { ratingTone } from '../lib/format'

/**
 * An info icon that reveals a plain-language explanation on hover or keyboard
 * focus. Visibility is driven by React state (rather than CSS :hover) so it
 * behaves consistently. `align` controls which edge the tooltip anchors to so
 * it stays on screen (use 'right' near the right edge of a card).
 */
export function InfoTip({
  text,
  align = 'left',
  className = '',
}: {
  text: string
  align?: 'left' | 'center' | 'right'
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const pos =
    align === 'right'
      ? 'right-0'
      : align === 'center'
        ? 'left-1/2 -translate-x-1/2'
        : 'left-0'
  return (
    <span
      className={'relative inline-flex align-middle ' + className}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label="More information"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="text-slate-500 transition-colors hover:text-slate-300 focus:text-slate-300 focus:outline-none"
      >
        <Info size={14} />
      </button>
      {open && (
        <span
          role="tooltip"
          className={
            'pointer-events-none absolute top-full z-40 mt-2 w-64 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-normal normal-case leading-relaxed tracking-normal text-slate-200 shadow-xl ' +
            pos
          }
        >
          {text}
        </span>
      )}
    </span>
  )
}

/** Colored initial bubble standing in for a company logo. */
export function TickerMark({
  ticker,
  size = 'md',
}: {
  ticker: string
  size?: 'sm' | 'md'
}) {
  const palette = [
    'from-sky-400 to-sky-600',
    'from-violet-400 to-violet-600',
    'from-amber-400 to-amber-600',
    'from-emerald-400 to-emerald-600',
    'from-rose-400 to-rose-600',
    'from-indigo-400 to-indigo-600',
  ]
  const idx =
    ticker.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % palette.length
  const dims = size === 'sm' ? 'h-6 w-6 text-[9px]' : 'h-7 w-7 text-[10px]'
  return (
    <div
      className={
        'grid shrink-0 place-items-center rounded-full bg-gradient-to-br font-bold text-slate-950 ' +
        dims +
        ' ' +
        palette[idx]
      }
    >
      {ticker.slice(0, 1)}
    </div>
  )
}

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

/**
 * A clickable table header that drives sorting for one column. Generic over
 * the column-key type so both server-side (Watchlist) and client-side
 * (Dashboard) sortable tables can share it.
 */
export function SortHeader<T extends string>({
  label,
  col,
  sortBy,
  sortDir,
  onSort,
  align = 'left',
  info,
  subLabel,
}: {
  label: string
  col: T
  sortBy: T
  sortDir: 'asc' | 'desc'
  onSort: (col: T) => void
  align?: 'left' | 'right'
  info?: string
  subLabel?: string
}) {
  const active = sortBy === col
  const Icon = !active ? ArrowDownUp : sortDir === 'asc' ? ArrowUp : ArrowDown
  return (
    <th
      className="px-4 py-3 font-medium"
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <span
        className={
          'inline-flex items-center gap-1 ' +
          (align === 'right' ? 'justify-end' : '')
        }
      >
        <button
          type="button"
          onClick={() => onSort(col)}
          aria-label={`Sort by ${label}`}
          className={
            'inline-flex items-center gap-1 transition-colors hover:text-slate-200 ' +
            (active ? 'text-slate-200' : '')
          }
        >
          {label}
          <Icon
            size={12}
            className={active ? 'text-emerald-400' : 'text-slate-600'}
          />
        </button>
        {info && <InfoTip text={info} />}
      </span>
      {subLabel && (
        <span className="block text-[10px] normal-case text-slate-600">
          {subLabel}
        </span>
      )}
    </th>
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
