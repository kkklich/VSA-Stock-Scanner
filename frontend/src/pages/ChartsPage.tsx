// Stock detail / charts page — the "detail" half of the master–detail dashboard.
// Now backed by GET /api/stocks/{ticker}/signals via the useStockDetail hook.

import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  MoreHorizontal,
  RotateCcw,
} from 'lucide-react'
import { StockChart } from '../components/StockChart'
import { CompanyPicker } from '../components/CompanyPicker'
import { AiAnalysisCard } from '../components/AiAnalysisCard'
import { TrustScoreCard } from '../components/TrustScoreCard'
import { RatingHistoryCard } from '../components/RatingHistoryCard'
import { Card, CardTitle, InfoTip } from '../components/ui'
import { useStockDetail } from '../hooks/useStockDetail'
import { useFundamentals } from '../hooks/useFundamentals'
import type { Candle, SignalFlag, VsaSignal } from '../types'
import {
  deltaTone,
  fmtCompactPln,
  fmtPct,
  fmtPrice,
  fmtSigned,
  ratingTone,
} from '../lib/format'

// ── Signal filtering (driven by the detection-settings panel) ─────────────────

const DEFAULT_SENSITIVITY = 60
const DEFAULT_CONTEXT_WINDOW = 120

// ── Chart time ranges ─────────────────────────────────────────────────────────

/**
 * Selectable chart horizons. `months` drives the API `fromDate` (null = as far
 * back as stored data goes); `sessions` is the matching signal context window
 * (~21 trading sessions per month) applied when the user picks the range.
 */
const RANGE_OPTIONS = [
  { key: '3M', months: 3, sessions: 63 },
  { key: '6M', months: 6, sessions: 126 },
  { key: '1Y', months: 12, sessions: 252 },
  { key: '2Y', months: 24, sessions: 504 },
  { key: 'MAX', months: null, sessions: 2520 },
] as const

type RangeKey = (typeof RANGE_OPTIONS)[number]['key']

const DEFAULT_RANGE: RangeKey = '1Y'

/** API `fromDate` (YYYY-MM-DD) for a range; MAX asks far enough back for everything. */
function rangeFromDate(key: RangeKey): string {
  const opt = RANGE_OPTIONS.find((r) => r.key === key)
  const d = new Date()
  if (opt?.months == null) return '2000-01-01'
  d.setMonth(d.getMonth() - opt.months)
  return d.toISOString().slice(0, 10)
}

/**
 * Relative "strength" of each VSA signal, 0–100. Used by the sensitivity
 * control: a lower sensitivity only surfaces the strongest signals, a higher
 * one also reveals weaker ones. Unknown names fall back to a mid value.
 */
const SIGNAL_STRENGTH: Record<string, number> = {
  sos: 90,
  'sign of strength': 90,
  sow: 88,
  'sign of weakness': 88,
  spring: 85,
  upthrust: 80,
  shakeout: 75,
  'stopping volume': 70,
  'successful test': 62,
  test: 55,
  'no demand': 50,
}

function signalStrength(name: string): number {
  return SIGNAL_STRENGTH[name.toLowerCase()] ?? 60
}

/**
 * Filter the raw signals by the detection settings:
 *  - sensitivity: keep signals whose strength ≥ (100 − sensitivity).
 *  - contextWindow: keep only signals within the last N trading sessions.
 */
function filterSignals(
  signals: VsaSignal[],
  history: Candle[],
  sensitivity: number,
  contextWindow: number,
): VsaSignal[] {
  const threshold = 100 - sensitivity
  const cutoff =
    history.length > contextWindow
      ? history[history.length - contextWindow].time
      : ''
  return signals.filter(
    (s) =>
      signalStrength(s.signalName) >= threshold &&
      (cutoff === '' || s.date >= cutoff),
  )
}

// ── Signal checklist derivation ──────────────────────────────────────────────

const STRENGTH_SIGNAL_NAMES = ['Spring', 'Successful Test', 'SOS']
const WEAKNESS_SIGNAL_NAMES = ['Upthrust', 'No Demand', 'SOW']

function deriveSignalFlags(vsaSignals: VsaSignal[]): {
  strength: SignalFlag[]
  weakness: SignalFlag[]
} {
  // Most recent occurrence of each signal name (signals are oldest-first).
  const lastOccurrence = new Map<string, string>()
  for (const s of vsaSignals) {
    lastOccurrence.set(s.signalName, s.date)
  }

  const strength: SignalFlag[] = STRENGTH_SIGNAL_NAMES.map((name) => ({
    name,
    present: lastOccurrence.has(name),
    date: lastOccurrence.get(name) ?? '—',
  }))

  const weakness: SignalFlag[] = WEAKNESS_SIGNAL_NAMES.map((name) => ({
    name,
    present: lastOccurrence.has(name),
    date: lastOccurrence.get(name) ?? '—',
  }))

  return { strength, weakness }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SignalRow({ flag }: { flag: SignalFlag }) {
  return (
    <li className="flex items-center justify-between py-1.5 text-sm">
      <span className="flex items-center gap-2">
        <span
          className={
            'grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold ' +
            (flag.present
              ? 'bg-emerald-500/20 text-emerald-400'
              : 'bg-rose-500/15 text-rose-400')
          }
        >
          {flag.present ? '✓' : '✕'}
        </span>
        <span className={flag.present ? 'text-slate-200' : 'text-slate-500'}>
          {flag.name}
        </span>
      </span>
      <span className="text-xs tabular-nums text-slate-500">{flag.date}</span>
    </li>
  )
}

function SignalChecklist({
  strength,
  weakness,
}: {
  strength: SignalFlag[]
  weakness: SignalFlag[]
}) {
  return (
    <Card className="flex flex-col">
      <CardTitle>
        Market strength{' '}
        <InfoTip text="Bullish VSA patterns detected for this stock in the shown period, with the date each last fired. ✓ = detected, ✕ = not present. Spring = trapped sellers below support; Successful Test = quiet retest of lows; SOS = strong buying bar." />
      </CardTitle>
      <ul className="px-4 pb-3">
        {strength.map((f) => (
          <SignalRow key={f.name} flag={f} />
        ))}
      </ul>
      <div className="border-t border-slate-800" />
      <CardTitle>
        Market weakness{' '}
        <InfoTip text="Bearish VSA patterns detected for this stock. Upthrust = trapped buyers above resistance; No Demand = quiet up-bar without professional interest; SOW = strong selling bar." />
      </CardTitle>
      <ul className="px-4 pb-4">
        {weakness.map((f) => (
          <SignalRow key={f.name} flag={f} />
        ))}
      </ul>
    </Card>
  )
}

function DetectionSettings({
  sensitivity,
  contextWindow,
  maxWindow,
  shown,
  total,
  onSensitivity,
  onContextWindow,
  onReset,
}: {
  sensitivity: number
  contextWindow: number
  maxWindow: number
  shown: number
  total: number
  onSensitivity: (v: number) => void
  onContextWindow: (v: number) => void
  onReset: () => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium text-slate-300">
            Adjust context for signal-detection sensitivity
          </span>
          <InfoTip text="Filters which VSA signals appear on the chart and in the Strength / Weakness checklist. Sensitivity: higher reveals more (and weaker) signals; lower shows only the strongest. Context window: only signals from the last N trading sessions are shown." />
        </div>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="text-slate-500 hover:text-slate-300"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand settings' : 'Collapse settings'}
        >
          {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>

      {!collapsed && (
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between">
            <label className="text-xs text-slate-500">Sensitivity</label>
            <span className="text-xs tabular-nums text-slate-300">
              {sensitivity}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={sensitivity}
            onChange={(e) => onSensitivity(+e.target.value)}
            className="mb-4 w-full accent-emerald-500"
          />

          <label className="mb-1 block text-xs text-slate-500">
            Context window (sessions)
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="number"
              min={5}
              max={maxWindow}
              value={contextWindow}
              onChange={(e) => {
                const n = Number(e.target.value)
                if (Number.isNaN(n)) return
                onContextWindow(Math.max(5, Math.min(maxWindow, n)))
              }}
              className="w-20 rounded-md border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 focus:border-emerald-500/50 focus:outline-none"
            />
            <button
              onClick={onReset}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
            >
              <RotateCcw size={13} /> Reset
            </button>
            <span className="ml-auto text-xs text-slate-500">
              Showing <span className="text-emerald-400">{shown}</span> / {total}{' '}
              signals
            </span>
          </div>
        </div>
      )}
    </Card>
  )
}

function FundamentalsCard({
  ticker,
  sector,
}: {
  ticker: string
  sector: string | null
}) {
  const { data, loading } = useFundamentals(ticker)
  const m = data?.metrics

  // Yahoo returns the dividend yield either as a fraction (0.056) or as a
  // percentage (5.6) depending on the data vintage — normalise to percent.
  const divYield =
    m?.dividendYield == null
      ? null
      : m.dividendYield < 1
        ? m.dividendYield * 100
        : m.dividendYield

  const rows: [string, string][] = [
    ['Sector', data?.sector ?? sector ?? '—'],
    ['Industry', data?.industry ?? '—'],
    ['Market cap', m?.marketCap != null ? `${fmtCompactPln(m.marketCap)} PLN` : '—'],
    ['P/E', m?.peRatio != null ? m.peRatio.toFixed(1) : '—'],
    ['EPS', m?.eps != null ? m.eps.toFixed(2) : '—'],
    ['Dividend yield', divYield != null ? `${divYield.toFixed(2)}%` : '—'],
    ['Employees', data?.employees != null ? data.employees.toLocaleString('en-US') : '—'],
  ]

  return (
    <Card>
      <CardTitle>
        Fundamentals{' '}
        <InfoTip text="Company fundamentals from Yahoo Finance, refreshed daily. Market cap = market value of all shares; P/E = price divided by yearly earnings per share (lower can mean cheaper); EPS = earnings per share; Dividend yield = yearly dividend as % of the price." />
      </CardTitle>
      <dl className="space-y-2 px-4 pb-4 text-sm">
        {loading && !data ? (
          <div className="flex items-center gap-2 py-2 text-slate-500">
            <Loader2 size={14} className="animate-spin" /> Loading…
          </div>
        ) : (
          <>
            {rows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt>
                <dd className="text-right font-medium text-slate-200">{v}</dd>
              </div>
            ))}
            {data?.website && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">WWW</dt>
                <dd className="text-right font-medium">
                  <a
                    href={data.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-400 hover:underline"
                  >
                    {data.website.replace(/^https?:\/\/(www\.)?/, '')}
                    <ExternalLink size={12} />
                  </a>
                </dd>
              </div>
            )}
            {data?.description && (
              <p className="border-t border-slate-800 pt-3 text-xs leading-relaxed text-slate-400">
                {data.description.length > 260
                  ? data.description.slice(0, 260) + '…'
                  : data.description}
              </p>
            )}
          </>
        )}
      </dl>
    </Card>
  )
}

function RatingCard({
  currentRating,
  ratingChange,
}: {
  currentRating: number
  ratingChange: number
}) {
  const tone = ratingTone(currentRating)
  return (
    <Card>
      <CardTitle right={<MoreHorizontal size={16} className="text-slate-600" />}>
        VSA Rating{' '}
        <InfoTip text="0–100 score built from all detected VSA signals with time decay: recent signals count more, old ones fade out (half impact after ~30 days). Above 70 = strong accumulation (green), around 50 = neutral, below 30 = distribution (red)." />
      </CardTitle>
      <div className="px-4 pb-4">
        <div className="flex items-end gap-2">
          <span className={'text-5xl font-bold tabular-nums ' + tone.text}>
            {currentRating}
          </span>
          <span className="mb-1 text-xs text-slate-500">/ 100</span>
        </div>
        <div className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-500">Rating change</span>
            <span className={deltaTone(ratingChange)}>
              {fmtSigned(ratingChange)}
            </span>
          </div>
        </div>
      </div>
    </Card>
  )
}

// ── Loading / error placeholders ──────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="flex flex-col items-center gap-4 text-slate-400">
        <Loader2 size={36} className="animate-spin text-emerald-500" />
        <p className="text-sm">Loading chart data…</p>
      </div>
    </div>
  )
}

function ErrorState({ message, ticker }: { message: string; ticker: string }) {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="max-w-md rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-center">
        <p className="font-semibold text-rose-300">{ticker.toUpperCase()} — failed to load</p>
        <p className="mt-1 text-sm text-slate-400">{message}</p>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ChartsPage() {
  const { ticker = 'kgh' } = useParams<{ ticker: string }>()

  // Chart time range — drives the fromDate sent to the signals endpoint.
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE)
  const fromDate = useMemo(() => rangeFromDate(range), [range])
  const { data, loading, error } = useStockDetail(ticker, fromDate)

  // Detection-settings state — drives which signals are shown on the chart
  // and in the strength/weakness checklist.
  const [sensitivity, setSensitivity] = useState(DEFAULT_SENSITIVITY)
  const [contextWindow, setContextWindow] = useState(DEFAULT_CONTEXT_WINDOW)

  // Picking a range also widens the signal context window to cover it, so
  // markers appear across the whole visible chart, not just the recent part.
  function selectRange(key: RangeKey) {
    setRange(key)
    const opt = RANGE_OPTIONS.find((r) => r.key === key)
    if (opt) setContextWindow(opt.sessions)
  }

  const visibleSignals = useMemo(
    () =>
      data
        ? filterSignals(data.vsaSignals, data.history, sensitivity, contextWindow)
        : [],
    [data, sensitivity, contextWindow],
  )

  const { strength, weakness } = useMemo(
    () => deriveSignalFlags(visibleSignals),
    [visibleSignals],
  )

  if (loading && !data) return <LoadingState />
  if (error) return <ErrorState message={error} ticker={ticker} />
  if (!data) return null

  const tone = ratingTone(data.currentRating)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      {/* Asset header */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <CompanyPicker ticker={data.ticker} name={data.name} />
        <span className="text-xl font-semibold text-slate-200">
          {fmtPrice(data.lastPrice)} PLN
        </span>
        <span className={'text-sm font-medium ' + deltaTone(data.priceChangePct)}>
          {fmtPct(data.priceChangePct)}
        </span>
        <span
          className={
            'ml-auto rounded-md px-2.5 py-1 text-sm font-semibold ring-1 ring-inset ' +
            tone.badge
          }
        >
          VSA {data.currentRating}
        </span>
      </div>

      {/* Three-column detail grid */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[260px_minmax(0,1fr)_300px]">
        {/* Left: signal checklist */}
        <SignalChecklist strength={strength} weakness={weakness} />

        {/* Center: detection settings + chart */}
        <div className="flex min-w-0 flex-col gap-4">
          <DetectionSettings
            sensitivity={sensitivity}
            contextWindow={contextWindow}
            maxWindow={Math.max(5, data.history.length)}
            shown={visibleSignals.length}
            total={data.vsaSignals.length}
            onSensitivity={setSensitivity}
            onContextWindow={setContextWindow}
            onReset={() => {
              setSensitivity(DEFAULT_SENSITIVITY)
              setContextWindow(DEFAULT_CONTEXT_WINDOW)
            }}
          />
          <Card className="p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 px-1">
              <span className="flex items-center gap-2 text-sm font-medium text-slate-300">
                {data.ticker} · 1D
                <span className="text-xs font-normal text-slate-500">
                  {data.history.length} sessions
                </span>
                {loading && (
                  <Loader2 size={14} className="animate-spin text-slate-500" />
                )}
              </span>
              <div
                role="group"
                aria-label="Chart time range"
                className="flex overflow-hidden rounded-lg border border-slate-700"
              >
                {RANGE_OPTIONS.map(({ key }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => selectRange(key)}
                    title={
                      key === 'MAX'
                        ? 'All stored history'
                        : `Last ${key.replace('M', ' months').replace('Y', ' year(s)')}`
                    }
                    className={
                      'px-2.5 py-1 text-xs font-medium transition-colors ' +
                      (range === key
                        ? 'bg-slate-700 text-slate-100'
                        : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
                    }
                  >
                    {key}
                  </button>
                ))}
              </div>
            </div>
            <div className="h-[300px] w-full sm:h-[420px]">
              <StockChart candles={data.history} signals={visibleSignals} />
            </div>
          </Card>
          <RatingHistoryCard ticker={ticker} />
        </div>

        {/* Right: fundamentals / rating / AI insight */}
        <div className="flex flex-col gap-4">
          <FundamentalsCard ticker={ticker} sector={data.sector} />
          <RatingCard
            currentRating={data.currentRating}
            ratingChange={data.ratingChange}
          />
          <AiAnalysisCard ticker={ticker} />
          <TrustScoreCard ticker={ticker} />
        </div>
      </div>
    </div>
  )
}
