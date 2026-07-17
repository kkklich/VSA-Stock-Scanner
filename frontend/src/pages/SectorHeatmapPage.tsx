// Sector heatmap page — a Finviz-style treemap of the ranked GPW universe.
// Stocks are grouped into sector blocks; tile SIZE is the market cap and tile
// COLOR is either the VSA rating (default view) or the price change over the
// selected horizon (1D / 1M / 1Y / MAX of stored history). Clicking a tile
// opens the stock's chart page.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { InfoTip } from '../components/ui'
import { useHeatmap } from '../hooks/useHeatmap'
import { usePersistentState } from '../hooks/usePersistentState'
import type { ApiHeatmapItem } from '../api/stocksApi'
import { fmtCompactPln, fmtPct } from '../lib/format'

/* ── Color modes ────────────────────────────────────────────────────────── */

type ColorMode = 'rating' | '1d' | '1m' | '1y' | 'max'

const MODES: { id: ColorMode; label: string; hint: string }[] = [
  { id: 'rating', label: 'Rating', hint: 'Color = VSA rating (0 red … 100 green)' },
  { id: '1d', label: '1D', hint: 'Color = price change vs the previous close' },
  { id: '1m', label: '1M', hint: 'Color = price change vs ~1 month ago' },
  { id: '1y', label: '1Y', hint: 'Color = price change vs ~1 year ago' },
  { id: 'max', label: 'MAX', hint: 'Color = price change over the full available history' },
]

/** Full-color saturation point (±%) for each change horizon. */
const CHANGE_SCALE: Record<Exclude<ColorMode, 'rating'>, number> = {
  '1d': 3,
  '1m': 10,
  '1y': 30,
  max: 60,
}

function changeFor(item: ApiHeatmapItem, mode: Exclude<ColorMode, 'rating'>) {
  switch (mode) {
    case '1d':
      return item.change1D
    case '1m':
      return item.change1M
    case '1y':
      return item.change1Y
    case 'max':
      return item.changeMax
  }
}

/* ── Colors ─────────────────────────────────────────────────────────────── */

const NEG: [number, number, number] = [244, 63, 94] // rose-500  #F43F5E
const MID: [number, number, number] = [51, 65, 85] // slate-700 #334155
const POS: [number, number, number] = [16, 185, 129] // emerald-500 #10B981
const MISSING_BG = '#1E293B' // slate-800 — horizon not available for this stock

function mix(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): string {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

/** Diverging rose → slate → emerald color for t in [-1, +1]. */
function diverging(t: number): string {
  const clamped = Math.max(-1, Math.min(1, t))
  return clamped < 0 ? mix(MID, NEG, -clamped) : mix(MID, POS, clamped)
}

function tileColor(item: ApiHeatmapItem, mode: ColorMode): string {
  if (mode === 'rating') return diverging((item.currentRating - 50) / 50)
  const change = changeFor(item, mode)
  if (change === null) return MISSING_BG
  return diverging(change / CHANGE_SCALE[mode])
}

function tileValueLabel(item: ApiHeatmapItem, mode: ColorMode): string {
  if (mode === 'rating') return String(item.currentRating)
  const change = changeFor(item, mode)
  return change === null ? '—' : fmtPct(change)
}

/* ── Squarified treemap layout ──────────────────────────────────────────── */

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

/**
 * Squarified treemap (Bruls et al.): splits `rect` into one sub-rectangle per
 * value, areas proportional to the values, keeping tiles close to square.
 * Values must be positive and sorted descending for best results.
 */
function squarify(values: number[], rect: Rect): Rect[] {
  const rects: Rect[] = values.map(() => ({ x: rect.x, y: rect.y, w: 0, h: 0 }))
  const total = values.reduce((a, b) => a + b, 0)
  if (total <= 0 || rect.w <= 0 || rect.h <= 0) return rects

  // Scale values so they sum to the rectangle's area.
  const areas = values.map((v) => (v / total) * rect.w * rect.h)

  let { x, y, w, h } = rect
  let start = 0
  while (start < areas.length) {
    // Lay the next row along the shorter edge; greedily grow it while the
    // worst tile aspect ratio keeps improving.
    const horizontal = w >= h // row is a vertical strip on the left
    const side = horizontal ? h : w
    let end = start
    let sum = 0
    let best = Infinity
    while (end < areas.length) {
      const trySum = sum + areas[end]
      const thickness = trySum / side
      let worst = 0
      for (let i = start; i <= end; i++) {
        const len = areas[i] / thickness
        worst = Math.max(worst, thickness / len, len / thickness)
      }
      if (worst <= best) {
        best = worst
        sum = trySum
        end++
      } else {
        break
      }
    }

    const thickness = sum / side
    let offset = 0
    for (let i = start; i < end; i++) {
      const len = areas[i] / thickness
      rects[i] = horizontal
        ? { x, y: y + offset, w: thickness, h: len }
        : { x: x + offset, y, w: len, h: thickness }
      offset += len
    }
    if (horizontal) {
      x += thickness
      w -= thickness
    } else {
      y += thickness
      h -= thickness
    }
    start = end
  }
  return rects
}

/* ── Layout data shapes ─────────────────────────────────────────────────── */

interface TileDatum {
  item: ApiHeatmapItem
  value: number
}

interface PlacedTile extends TileDatum {
  rect: Rect
}

interface PlacedSector {
  sector: string
  rect: Rect
  headerH: number
  tiles: PlacedTile[]
}

const SECTOR_PAD = 1.5
const SECTOR_HEADER_H = 15

function buildLayout(groups: { sector: string; tiles: TileDatum[] }[], w: number, h: number): PlacedSector[] {
  const totals = groups.map((g) => g.tiles.reduce((a, t) => a + t.value, 0))
  const sectorRects = squarify(totals, { x: 0, y: 0, w, h })
  return groups.map((g, gi) => {
    const r = sectorRects[gi]
    const headerH = r.h >= 44 && r.w >= 56 ? SECTOR_HEADER_H : 0
    const inner: Rect = {
      x: r.x + SECTOR_PAD,
      y: r.y + SECTOR_PAD + headerH,
      w: Math.max(0, r.w - SECTOR_PAD * 2),
      h: Math.max(0, r.h - SECTOR_PAD * 2 - headerH),
    }
    const tileRects = squarify(g.tiles.map((t) => t.value), inner)
    return {
      sector: g.sector,
      rect: r,
      headerH,
      tiles: g.tiles.map((t, i) => ({ ...t, rect: tileRects[i] })),
    }
  })
}

/* ── Legend ─────────────────────────────────────────────────────────────── */

function Legend({ mode }: { mode: ColorMode }) {
  const gradient = `linear-gradient(to right, rgb(${NEG.join(',')}), rgb(${MID.join(',')}), rgb(${POS.join(',')}))`
  const scale = mode === 'rating' ? null : CHANGE_SCALE[mode]
  const [lo, mid, hi] =
    scale === null ? ['0', '50', '100'] : [`-${scale}%`, '0%', `+${scale}%`]
  return (
    <div className="flex items-center gap-2 text-[11px] text-slate-500">
      <span className="tabular-nums">{lo}</span>
      <div
        className="h-2 w-28 rounded-full sm:w-36"
        style={{ background: gradient }}
      />
      <span className="tabular-nums">{hi}</span>
      <span className="hidden text-slate-600 sm:inline">· mid {mid}</span>
    </div>
  )
}

/* ── Tooltip ────────────────────────────────────────────────────────────── */

interface TooltipState {
  item: ApiHeatmapItem
  x: number
  y: number
}

function HeatmapTooltip({
  tip,
  containerW,
  containerH,
}: {
  tip: TooltipState
  containerW: number
  containerH: number
}) {
  const width = 230
  const height = 190 // approximate rendered height, used only for clamping
  const left = Math.min(Math.max(tip.x + 14, 4), Math.max(4, containerW - width - 4))
  // Flip above the cursor when the tooltip would clip past the bottom edge.
  const top =
    tip.y + 16 + height > containerH
      ? Math.max(4, tip.y - 16 - height)
      : tip.y + 16
  const rows: [string, string][] = [
    ['Price', `${tip.item.lastPrice.toFixed(2)} PLN`],
    [
      'Market cap',
      tip.item.marketCap === null ? '—' : fmtCompactPln(tip.item.marketCap),
    ],
    ['VSA rating', String(tip.item.currentRating)],
    ['Signal', tip.item.lastSignal],
    ['1D', tip.item.change1D === null ? '—' : fmtPct(tip.item.change1D)],
    ['1M', tip.item.change1M === null ? '—' : fmtPct(tip.item.change1M)],
    ['1Y', tip.item.change1Y === null ? '—' : fmtPct(tip.item.change1Y)],
    ['MAX', tip.item.changeMax === null ? '—' : fmtPct(tip.item.changeMax)],
  ]
  return (
    <div
      className="pointer-events-none absolute z-30 rounded-lg border border-slate-700 bg-slate-800/95 px-3 py-2 text-xs shadow-xl"
      style={{ left, top, width }}
    >
      <div className="mb-1 font-semibold text-slate-100">
        {tip.item.ticker}
        <span className="ml-1.5 font-normal text-slate-400">{tip.item.name}</span>
      </div>
      <div className="mb-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        {tip.item.sector ?? 'Other'}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-slate-500">{k}</dt>
            <dd className="tabular-nums text-slate-200">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export function SectorHeatmapPage() {
  const { data, loading, error, refetch } = useHeatmap()
  const [mode, setMode] = usePersistentState<ColorMode>(
    'stockpilot:heatmap:colorMode',
    'rating',
  )
  const [tip, setTip] = useState<TooltipState | null>(null)
  const navigate = useNavigate()

  // Measure the treemap container so the layout fills it exactly.
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      setSize((prev) =>
        prev.w === r.width && prev.h === r.height
          ? prev
          : { w: r.width, h: r.height },
      )
    }
    // Measure immediately — don't depend on the observer's first delivery.
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    // ResizeObserver deliveries are suspended in hidden/background tabs, and
    // the mount-time measurement can catch a not-yet-settled layout — so also
    // re-measure on window resize, on visibility changes, and whenever a
    // fetch completes (the [data] dependency re-runs this effect).
    window.addEventListener('resize', measure)
    document.addEventListener('visibilitychange', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
      document.removeEventListener('visibilitychange', measure)
    }
  }, [data])

  const items = useMemo(() => data?.items ?? [], [data])

  // Tiles without a known market cap get the smallest known cap so they stay
  // visible (drawn at minimum size) instead of disappearing from the map.
  const groups = useMemo(() => {
    if (items.length === 0) return []
    const knownCaps = items
      .filter((i) => i.marketCap !== null)
      .map((i) => i.marketCap as number)
    const fallbackCap =
      knownCaps.length > 0 ? Math.min(...knownCaps) : 100_000_000
    const bySector = new Map<string, TileDatum[]>()
    for (const item of items) {
      const sector = item.sector ?? 'Other'
      const tile: TileDatum = { item, value: item.marketCap ?? fallbackCap }
      const list = bySector.get(sector)
      if (list) list.push(tile)
      else bySector.set(sector, [tile])
    }
    return [...bySector.entries()]
      .map(([sector, tiles]) => ({
        sector,
        tiles: tiles.sort((a, b) => b.value - a.value),
      }))
      .sort(
        (a, b) =>
          b.tiles.reduce((s, t) => s + t.value, 0) -
          a.tiles.reduce((s, t) => s + t.value, 0),
      )
  }, [items])

  const layout = useMemo(
    () => (size.w > 0 && size.h > 0 ? buildLayout(groups, size.w, size.h) : []),
    [groups, size],
  )

  const unknownCapCount = items.filter((i) => i.marketCap === null).length
  const activeHint = MODES.find((m) => m.id === mode)?.hint ?? ''

  return (
    <div className="flex h-full flex-col p-4 sm:p-6">
      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-1.5 text-lg font-semibold text-slate-100">
            Sector heatmap
            <InfoTip text="Every ranked GPW stock as one tile, grouped by sector. Tile size = market cap. Tile color = VSA rating, or the price change over the selected period. Click a tile to open the stock's chart." />
          </h2>
          <p className="text-sm text-slate-500">
            Size = market cap · {activeHint.toLowerCase()}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Legend mode={mode} />
          <div
            role="group"
            aria-label="Tile color"
            className="flex overflow-hidden rounded-lg border border-slate-700"
          >
            {MODES.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                title={MODES.find((m) => m.id === id)?.hint}
                className={
                  'px-3 py-1.5 text-xs font-medium transition-colors ' +
                  (mode === id
                    ? 'bg-slate-700 text-slate-100'
                    : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
                }
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Treemap */}
      <div
        ref={containerRef}
        onMouseLeave={() => setTip(null)}
        className="relative min-h-[420px] flex-1 overflow-hidden rounded-xl border border-slate-800 bg-slate-950"
      >
        {loading && (
          <div className="absolute inset-0 z-20 grid place-items-center bg-slate-950/80">
            <div className="flex flex-col items-center gap-3 text-sm text-slate-400">
              <Loader2 className="animate-spin text-emerald-400" size={22} />
              Building the heatmap — the first run after a restart can take a
              moment…
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="absolute inset-0 z-20 grid place-items-center bg-slate-950/80">
            <div className="text-center text-sm">
              <p className="mb-2 text-rose-400">Could not load the heatmap: {error}</p>
              <button
                type="button"
                onClick={refetch}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 transition-colors hover:bg-slate-800"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && data && items.length === 0 && (
          <div className="absolute inset-0 z-10 grid place-items-center">
            <div className="px-6 text-center text-sm text-slate-500">
              <p>No stocks to display yet.</p>
              <p className="mt-1">
                Tiles appear once ranked data is available — run a refresh from
                the Dashboard, then come back.
              </p>
            </div>
          </div>
        )}

        {layout.map((sector) => (
          <div key={sector.sector}>
            {sector.headerH > 0 && (
              <div
                className="absolute truncate text-[9px] font-semibold uppercase tracking-wider text-slate-500"
                style={{
                  left: sector.rect.x + SECTOR_PAD + 2,
                  top: sector.rect.y + 1,
                  width: Math.max(0, sector.rect.w - SECTOR_PAD * 2 - 4),
                }}
              >
                {sector.sector}
              </div>
            )}
            {sector.tiles.map(({ item, rect }) => {
              if (rect.w < 1 || rect.h < 1) return null
              const showValue = rect.w >= 52 && rect.h >= 34
              const showTicker = rect.w >= 30 && rect.h >= 14
              const fontSize = Math.max(
                9,
                Math.min(16, Math.sqrt(rect.w * rect.h) / 6),
              )
              return (
                <button
                  key={item.ticker}
                  type="button"
                  onClick={() => navigate(`/stock/${item.ticker.toLowerCase()}`)}
                  onMouseMove={(e) => {
                    const box = containerRef.current?.getBoundingClientRect()
                    if (!box) return
                    setTip({
                      item,
                      x: e.clientX - box.left,
                      y: e.clientY - box.top,
                    })
                  }}
                  onFocus={() =>
                    setTip({
                      item,
                      x: rect.x + rect.w / 2,
                      y: rect.y + rect.h / 2,
                    })
                  }
                  onBlur={() => setTip(null)}
                  aria-label={`${item.ticker} — ${item.name}`}
                  className="absolute overflow-hidden border border-slate-950 leading-tight transition-[filter] hover:brightness-125 focus:z-10 focus:outline focus:outline-1 focus:outline-slate-200"
                  style={{
                    left: rect.x,
                    top: rect.y,
                    width: rect.w,
                    height: rect.h,
                    backgroundColor: tileColor(item, mode),
                  }}
                >
                  {showTicker && (
                    <span
                      className="flex h-full w-full flex-col items-center justify-center px-0.5"
                      style={{ fontSize }}
                    >
                      <span className="max-w-full truncate font-bold text-white/95">
                        {item.ticker}
                      </span>
                      {showValue && (
                        <span
                          className="tabular-nums text-white/75"
                          style={{ fontSize: Math.max(8, fontSize - 3) }}
                        >
                          {tileValueLabel(item, mode)}
                        </span>
                      )}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        ))}

        {tip && (
          <HeatmapTooltip tip={tip} containerW={size.w} containerH={size.h} />
        )}
      </div>

      {/* Footer note */}
      <p className="mt-2 text-[11px] text-slate-600">
        {data?.asOf ? `Data as of ${data.asOf} · ` : ''}
        {items.length} stocks
        {unknownCapCount > 0
          ? ` · ${unknownCapCount} without a known market cap are drawn at minimum size`
          : ''}
        {' · MAX = change over the full available price history'}
      </p>
    </div>
  )
}
