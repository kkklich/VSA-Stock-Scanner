// Rating-history card for the stock detail page.
//
// Plots the stock's VSA rating (0–100) over time from the daily snapshots the
// refresh pipeline stores in the database — this is how you see whether a
// stock's "attractiveness" is building up or fading. Single series, fixed
// 0–100 axis so different stocks are directly comparable; dashed guides at 30
// and 70 mirror the red/green rating badge thresholds used across the app.

import { useMemo, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Card, CardTitle, InfoTip } from './ui'
import { useRatingHistory } from '../hooks/useRatingHistory'
import type { ApiRatingPoint } from '../api/stocksApi'

// ViewBox geometry (SVG units). The SVG scales to the card width.
const W = 600
const H = 190
const PAD = { top: 10, right: 14, bottom: 22, left: 30 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom

const x = (i: number, n: number) =>
  PAD.left + (n <= 1 ? PLOT_W / 2 : (i / (n - 1)) * PLOT_W)
const y = (rating: number) => PAD.top + (1 - rating / 100) * PLOT_H

const fmtDay = (iso: string) =>
  new Date(iso).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })

function buildPath(points: ApiRatingPoint[]): string {
  return points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i, points.length).toFixed(1)},${y(p.rating).toFixed(1)}`)
    .join(' ')
}

export function RatingHistoryCard({ ticker }: { ticker: string }) {
  const { data, loading, error } = useRatingHistory(ticker)
  const [hover, setHover] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  // Memoised so the `?? []` fallback is not a fresh array on every render,
  // which would re-run the two path memos below each time.
  const points = useMemo(() => data?.points ?? [], [data])
  const n = points.length

  const linePath = useMemo(() => buildPath(points), [points])
  const areaPath = useMemo(() => {
    if (n < 2) return ''
    return `${buildPath(points)} L${x(n - 1, n).toFixed(1)},${y(0)} L${x(0, n).toFixed(1)},${y(0)} Z`
  }, [points, n])

  // Map the pointer to the nearest data point (index space).
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (n < 2 || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    const idx = Math.round(((px - PAD.left) / PLOT_W) * (n - 1))
    setHover(Math.max(0, Math.min(n - 1, idx)))
  }

  const hovered = hover !== null ? points[hover] : null
  const last = n > 0 ? points[n - 1] : null

  return (
    <Card className="p-3">
      <div className="flex items-start justify-between px-1">
        <CardTitle>
          Rating history{' '}
          <InfoTip text="How this stock's VSA rating (0–100) changed day by day. Ratings are recalculated and saved after every data refresh (nightly at 18:00 or the Refresh button), so over time you can see whether smart-money accumulation is building or fading. Above 70 = strong (green zone), below 30 = weak (red zone)." />
        </CardTitle>
        {last && (
          <span className="pt-4 pr-1 text-xs tabular-nums text-slate-500">
            {fmtDay(points[0].date)} – {fmtDay(last.date)}
          </span>
        )}
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2 py-14 text-sm text-slate-500">
          <Loader2 size={15} className="animate-spin" /> Loading rating history…
        </div>
      )}

      {!loading && (error || n < 2) && (
        <p className="px-4 pb-4 pt-2 text-sm text-slate-500">
          {error
            ? `Could not load rating history: ${error}`
            : 'Not enough history yet — snapshots are saved with every data refresh, so the chart will build up day by day.'}
        </p>
      )}

      {!loading && !error && n >= 2 && (
        <div className="relative px-1 pb-1">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="h-auto w-full"
            role="img"
            aria-label={`VSA rating of ${ticker.toUpperCase()} over time, currently ${last?.rating}`}
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          >
            <defs>
              <linearGradient id="ratingFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-emerald-500)" stopOpacity="0.18" />
                <stop offset="100%" stopColor="var(--color-emerald-500)" stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* Recessive grid: badge thresholds (30 / 70) + midline */}
            {[
              { v: 70, cls: 'stroke-emerald-500/25' },
              { v: 50, cls: 'stroke-slate-700/60' },
              { v: 30, cls: 'stroke-rose-500/25' },
            ].map(({ v, cls }) => (
              <line
                key={v}
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(v)}
                y2={y(v)}
                strokeDasharray="3 4"
                strokeWidth="1"
                className={cls}
              />
            ))}

            {/* Y labels (text tokens, not series color) */}
            {[0, 30, 50, 70, 100].map((v) => (
              <text
                key={v}
                x={PAD.left - 6}
                y={y(v) + 3}
                textAnchor="end"
                className="fill-slate-500"
                fontSize="10"
              >
                {v}
              </text>
            ))}

            {/* X labels: first / middle / last date */}
            {[0, Math.floor((n - 1) / 2), n - 1].map((i, k, arr) =>
              arr.indexOf(i) === k ? (
                <text
                  key={i}
                  x={x(i, n)}
                  y={H - 6}
                  textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
                  className="fill-slate-500"
                  fontSize="10"
                >
                  {fmtDay(points[i].date)}
                </text>
              ) : null,
            )}

            {/* Area + 2px line */}
            <path d={areaPath} fill="url(#ratingFill)" />
            <path
              d={linePath}
              fill="none"
              stroke="var(--color-emerald-500)"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {/* Latest value: dot + direct label */}
            {last && (
              <>
                <circle cx={x(n - 1, n)} cy={y(last.rating)} r="3.5" fill="var(--color-emerald-500)" />
                <text
                  x={x(n - 1, n) - 6}
                  y={y(last.rating) - 8}
                  textAnchor="end"
                  className="fill-slate-200"
                  fontSize="11"
                  fontWeight="600"
                >
                  {last.rating}
                </text>
              </>
            )}

            {/* Hover crosshair */}
            {hovered && hover !== null && (
              <>
                <line
                  x1={x(hover, n)}
                  x2={x(hover, n)}
                  y1={PAD.top}
                  y2={H - PAD.bottom}
                  className="stroke-slate-600"
                  strokeWidth="1"
                />
                <circle
                  cx={x(hover, n)}
                  cy={y(hovered.rating)}
                  r="4"
                  fill="var(--color-emerald-500)"
                  className="stroke-slate-950"
                  strokeWidth="2"
                />
              </>
            )}
          </svg>

          {/* Tooltip (HTML, positioned over the SVG) */}
          {hovered && hover !== null && (
            <div
              className="pointer-events-none absolute top-1 z-10 -translate-x-1/2 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs shadow-lg"
              style={{
                left: `${((x(hover, n) / W) * 100).toFixed(2)}%`,
              }}
            >
              <div className="whitespace-nowrap text-slate-400">
                {new Date(hovered.date).toLocaleDateString('pl-PL')}
              </div>
              <div className="whitespace-nowrap font-semibold text-slate-100">
                Rating {hovered.rating}
                <span className="ml-1.5 font-normal text-slate-400">
                  {hovered.verdict}
                </span>
              </div>
            </div>
          )}

          {data?.source === 'computed' && (
            <p className="px-1 pt-1 text-[11px] text-slate-600">
              Derived from price history — daily snapshots will be stored in the
              database after the next refresh.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
