// Stock detail / charts page — the "detail" half of the master–detail dashboard.
// Now backed by GET /api/stocks/{ticker}/signals via the useStockDetail hook.

import { useCallback, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Trans, useTranslation } from 'react-i18next'
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  MoreHorizontal,
  RotateCcw,
} from 'lucide-react'
import { StockChart, type MethodOverlay, type VisibleSpan } from '../components/StockChart'
import {
  ChartMethodLegend,
  type ChartMethodLegendItem,
} from '../components/ChartMethodLegend'
import { CompanyPicker } from '../components/CompanyPicker'
import { AiAnalysisCard } from '../components/AiAnalysisCard'
import { TrustScoreCard } from '../components/TrustScoreCard'
import { AnalyticsSummaryCard } from '../components/AnalyticsSummaryCard'
import { RatingHistoryCard } from '../components/RatingHistoryCard'
import { VolumeCard } from '../components/VolumeCard'
import { InvestmentCard } from '../components/InvestmentCard'
import { Card, CardTitle, InfoTip } from '../components/ui'
import { useStockDetail } from '../hooks/useStockDetail'
import { useMethods } from '../hooks/useMethods'
import { usePersistentState } from '../hooks/usePersistentState'
import { useFundamentals } from '../hooks/useFundamentals'
import { useTickerVolume } from '../hooks/useTickerVolume'
import type { ApiFundamentals, ChartInterval } from '../api/stocksApi'
import type { Candle, SignalFlag, VsaSignal } from '../types'
import {
  deltaTone,
  fmtCompactPln,
  fmtPct,
  fmtPrice,
  fmtSigned,
  ratingTone,
  safeHttpUrl,
} from '../lib/format'
import { useChartPalette } from '../lib/chartTheme'

// ── Signal filtering (driven by the detection-settings panel) ─────────────────

const DEFAULT_SENSITIVITY = 60
const DEFAULT_CONTEXT_WINDOW = 120

// ── Trading-method chart overlays ─────────────────────────────────────────────

/** Method id whose overlay is the built-in VSA arrows (from `vsaSignals`). */
const VSA_METHOD_ID = 'vsa'
/*
 * VSA's marker/legend colour is the palette's bullish emerald; the OTHER
 * methods get `methodColors`, assigned in backend display order. Both come
 * from `lib/chartTheme` so they follow the light/dark theme — the light theme
 * uses darker shades that still read on white candlesticks.
 */

/** localStorage key for which methods are drawn on the stock chart. */
const CHART_METHODS_KEY = 'stockpilot:chart-methods:v1'

// ── Chart time ranges ─────────────────────────────────────────────────────────

/**
 * Selectable chart horizons. `months` drives the API `fromDate` (null = as far
 * back as stored data goes); `sessions` is the matching signal context window
 * (~21 trading sessions per month) applied when the user picks the range.
 */
/**
 * Selectable chart bar sizes, in the order they appear on the toolbar.
 *
 * `1d` is the app's native timeframe — the rating, the ranking and the trading
 * methods are all computed on daily bars, and stay daily whichever timeframe
 * the chart shows. The others change only what is drawn: `1w` is aggregated
 * from the same daily bars, and the intraday sizes are fetched live for the
 * chart (the app does not store intraday history, so how far back they reach is
 * capped by the data provider — see `maxDays`).
 *
 * `barsPerSession` converts a window in calendar days into a bar count for the
 * signal-context window; GPW trades 09:00–17:00, so a session is ~17 half-hour
 * bars, ~9 hourly, ~2 four-hourly, and a week is one weekly bar per 5 sessions.
 */
const INTERVAL_OPTIONS = [
  { key: '30m', label: '30m', barsPerSession: 17, maxDays: 60 },
  { key: '1h', label: '1H', barsPerSession: 9, maxDays: 730 },
  { key: '4h', label: '4H', barsPerSession: 2, maxDays: 730 },
  { key: '1d', label: '1D', barsPerSession: 1, maxDays: null },
  { key: '1w', label: '1W', barsPerSession: 0.2, maxDays: null },
] as const satisfies readonly {
  key: ChartInterval
  label: string
  barsPerSession: number
  maxDays: number | null
}[]

const DEFAULT_INTERVAL: ChartInterval = '1d'

/**
 * Time ranges offered per bar size. They differ because the useful — and the
 * *available* — window does: two years of 30-minute candles is both unreadable
 * and more than the provider serves, while three months of weekly ones is 13
 * candles. Each range is a number of calendar days back (`null` = everything
 * stored).
 */
const INTERVAL_RANGES: Record<
  ChartInterval,
  readonly { key: string; days: number | null }[]
> = {
  '30m': [
    { key: '5D', days: 7 },
    { key: '10D', days: 14 },
    { key: '1M', days: 30 },
    { key: '2M', days: 60 },
  ],
  '1h': [
    { key: '1M', days: 30 },
    { key: '3M', days: 92 },
    { key: '6M', days: 183 },
    { key: '1Y', days: 365 },
    { key: '2Y', days: 730 },
  ],
  '4h': [
    { key: '1M', days: 30 },
    { key: '3M', days: 92 },
    { key: '6M', days: 183 },
    { key: '1Y', days: 365 },
    { key: '2Y', days: 730 },
  ],
  '1d': [
    { key: '3M', days: 92 },
    { key: '6M', days: 183 },
    { key: '1Y', days: 365 },
    { key: '2Y', days: 730 },
    { key: 'MAX', days: null },
  ],
  '1w': [
    { key: '1Y', days: 365 },
    { key: '2Y', days: 730 },
    { key: '5Y', days: 1826 },
    { key: 'MAX', days: null },
  ],
}

/** Range each bar size opens on — enough candles to read, not so many they blur. */
const DEFAULT_RANGE: Record<ChartInterval, string> = {
  '30m': '1M',
  '1h': '3M',
  '4h': '6M',
  '1d': '1Y',
  '1w': '2Y',
}

function intervalOption(interval: ChartInterval) {
  return INTERVAL_OPTIONS.find((o) => o.key === interval) ?? INTERVAL_OPTIONS[3]
}

function rangesFor(interval: ChartInterval) {
  return INTERVAL_RANGES[interval]
}

/**
 * Signal-context window (in bars) that covers a range, so picking a range shows
 * markers across the whole visible chart rather than only its recent end.
 * ~252 trading sessions a year, times the bars each session produces.
 */
function contextBarsFor(interval: ChartInterval, days: number | null): number {
  const perSession = intervalOption(interval).barsPerSession
  const sessions = days == null ? 2520 : Math.round((days * 252) / 365)
  return Math.max(20, Math.round(sessions * perSession))
}

/**
 * Scroll-to-change-range tuning. "Show me further back" is either panning more
 * than `PAN_PAST_START_BARS` past the oldest loaded candle, or zooming out
 * until the viewport is `ZOOM_OUT_FACTOR` times wider than the loaded data
 * (which is what a wheel-zoom anchored near the right edge looks like — the
 * window grows past the newest bar rather than past the oldest one). Shrinking
 * the view below `ZOOM_IN_FRACTION` of the loaded bars means "show me a shorter
 * range". At rest the viewport is only a few bars wider than the data, so the
 * zoom-out factor has margin. The cooldown keeps one gesture to a single step.
 */
const PAN_PAST_START_BARS = 8
const ZOOM_OUT_FACTOR = 1.15
const ZOOM_IN_FRACTION = 0.3
const STEP_COOLDOWN_MS = 700

/** API `fromDate` (YYYY-MM-DD) for a range; MAX asks far enough back for everything. */
function rangeFromDate(interval: ChartInterval, key: string): string {
  const opt = rangesFor(interval).find((r) => r.key === key)
  if (opt?.days == null) return '2000-01-01'
  const d = new Date()
  d.setDate(d.getDate() - opt.days)
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

/**
 * Display form of a signal's bar time. Daily/weekly markers are already a bare
 * date; an intraday one arrives as a full ISO timestamp, which is far too long
 * for the checklist's right-hand column — trim it to "09-04 13:00", dropping
 * the year and the offset (every bar on the chart is exchange-local anyway).
 */
function formatSignalDate(value: string): string {
  if (!value.includes('T')) return value
  const [day, time = ''] = value.split('T')
  return `${day.slice(5)} ${time.slice(0, 5)}`
}

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
    date: formatSignalDate(lastOccurrence.get(name) ?? '—'),
  }))

  const weakness: SignalFlag[] = WEAKNESS_SIGNAL_NAMES.map((name) => ({
    name,
    present: lastOccurrence.has(name),
    date: formatSignalDate(lastOccurrence.get(name) ?? '—'),
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
  const { t } = useTranslation()
  return (
    <Card className="flex flex-col">
      <CardTitle>
        {t('chart.strength.title')}{' '}
        <InfoTip text={t('chart.strength.info')} />
      </CardTitle>
      <ul className="px-4 pb-3">
        {strength.map((f) => (
          <SignalRow key={f.name} flag={f} />
        ))}
      </ul>
      <div className="border-t border-slate-800" />
      <CardTitle>
        {t('chart.weakness.title')}{' '}
        <InfoTip text={t('chart.weakness.info')} />
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
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(false)
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium text-slate-300">
            {t('chart.detection.title')}
          </span>
          <InfoTip text={t('chart.detection.info')} />
        </div>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="text-slate-500 hover:text-slate-300"
          aria-expanded={!collapsed}
          aria-label={collapsed ? t('chart.detection.expand') : t('chart.detection.collapse')}
        >
          {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>

      {!collapsed && (
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between">
            <label className="text-xs text-slate-500">{t('chart.detection.sensitivity')}</label>
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
            {t('chart.detection.contextWindow')}
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
              <RotateCcw size={13} /> {t('chart.detection.reset')}
            </button>
            <span className="ml-auto text-xs text-slate-500">
              <Trans
                i18nKey="chart.detection.showing"
                values={{ shown, total }}
                components={[<span className="text-emerald-400" />]}
              />
            </span>
          </div>
        </div>
      )}
    </Card>
  )
}

/** Small uppercase divider inside the fundamentals card. */
function CardSection({ label, info }: { label: string; info?: string }) {
  return (
    <div className="flex items-center gap-1.5 border-t border-slate-800 pt-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
      {label}
      {info && <InfoTip text={info} />}
    </div>
  )
}

/** Percent value with directional colour; "—" when not available. */
function PctValue({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <span className="text-slate-600">—</span>
  return (
    <span className={'tabular-nums ' + deltaTone(pct)}>{fmtPct(pct)}</span>
  )
}

function FundamentalsCard({
  data,
  loading,
  sector,
}: {
  data: ApiFundamentals | null
  loading: boolean
  sector: string | null
}) {
  const { t } = useTranslation()
  const m = data?.metrics
  const r = data?.priceReturns

  // Yahoo already reports the dividend yield AS A PERCENT (KGHM: 0.51 = 0.51%,
  // cross-checked against dividendRate 1.5 PLN ÷ price 306 ≈ 0.49%). An older
  // "if < 1 it must be a fraction, so ×100" heuristic lived here and turned
  // every sub-1% yield into a wild 51%-style figure — never reintroduce it:
  // a fraction and a small percentage are indistinguishable from the value
  // alone, so trust the documented unit instead of guessing.
  const divYield = m?.dividendYield ?? null

  // ROE/ROA arrive as fractions (0.184 = 18.4%).
  const asPct = (v: number | null | undefined) =>
    v == null ? '—' : `${(v * 100).toFixed(1)}%`
  const asPln = (v: number | null | undefined) =>
    v == null ? '—' : `${fmtCompactPln(v)} PLN`

  const rows: [string, string][] = [
    [t('chart.fundamentals.sector'), data?.sector ?? sector ?? '—'],
    [t('chart.fundamentals.industry'), data?.industry ?? '—'],
    [t('chart.fundamentals.marketCap'), m?.marketCap != null ? `${fmtCompactPln(m.marketCap)} PLN` : '—'],
    [t('chart.fundamentals.pe'), m?.peRatio != null ? m.peRatio.toFixed(1) : '—'],
    [t('chart.fundamentals.eps'), m?.eps != null ? m.eps.toFixed(2) : '—'],
    [t('chart.fundamentals.dividendYield'), divYield != null ? `${divYield.toFixed(2)}%` : '—'],
    [t('chart.fundamentals.employees'), data?.employees != null ? data.employees.toLocaleString('en-US') : '—'],
  ]

  // Price returns. "Since …" always has a value once there are two bars, so
  // it is the honest fallback while the stored history is still short.
  const returnRows: [string, number | null | undefined][] = [
    [t('chart.fundamentals.thisYear'), r?.ytdPct],
    [t('chart.fundamentals.oneYear'), r?.y1Pct],
    [t('chart.fundamentals.threeYears'), r?.y3Pct],
    [t('chart.fundamentals.fiveYears'), r?.y5Pct],
  ]

  const incomeRows: [string, string][] = [
    [t('chart.fundamentals.revenue12m'), asPln(data?.ttmRevenue)],
    [t('chart.fundamentals.netIncome12m'), asPln(data?.ttmNetIncome)],
    [t('chart.fundamentals.roe'), asPct(m?.returnOnEquity)],
    [t('chart.fundamentals.roa'), asPct(m?.returnOnAssets)],
  ]

  // Investment spending (capex) has moved to its own InvestmentCard next to
  // this one — it is fed the same fundamentals payload, so no extra fetch.

  return (
    <Card>
      <CardTitle>
        {t('chart.fundamentals.title')}{' '}
        <InfoTip text={t('chart.fundamentals.info')} />
      </CardTitle>
      <dl className="space-y-2 px-4 pb-4 text-sm">
        {loading && !data ? (
          <div className="flex items-center gap-2 py-2 text-slate-500">
            <Loader2 size={14} className="animate-spin" /> {t('common.loading')}
          </div>
        ) : (
          <>
            {rows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt>
                <dd className="text-right font-medium text-slate-200">{v}</dd>
              </div>
            ))}

            <CardSection
              label={t('chart.fundamentals.priceReturn')}
              info={t('chart.fundamentals.priceReturnInfo')}
            />
            {returnRows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt>
                <dd className="text-right font-medium">
                  <PctValue pct={v} />
                </dd>
              </div>
            ))}
            {r?.maxPct != null && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">
                  {r.maxFromDate
                    ? t('chart.fundamentals.since', { date: r.maxFromDate })
                    : t('chart.fundamentals.allTime')}
                </dt>
                <dd className="text-right font-medium">
                  <PctValue pct={r.maxPct} />
                </dd>
              </div>
            )}

            <CardSection
              label={t('chart.fundamentals.income')}
              info={t('chart.fundamentals.incomeInfo')}
            />
            {incomeRows.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-slate-500">{k}</dt>
                <dd className="text-right font-medium text-slate-200">{v}</dd>
              </div>
            ))}

            {safeHttpUrl(data?.website) && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">{t('chart.fundamentals.www')}</dt>
                <dd className="text-right font-medium">
                  <a
                    href={safeHttpUrl(data?.website)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-400 hover:underline"
                  >
                    {data!.website!.replace(/^https?:\/\/(www\.)?/, '')}
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
  const { t } = useTranslation()
  const tone = ratingTone(currentRating)
  return (
    <Card>
      <CardTitle right={<MoreHorizontal size={16} className="text-slate-600" />}>
        {t('chart.rating.title')}{' '}
        <InfoTip text={t('chart.rating.info')} />
      </CardTitle>
      <div className="px-4 pb-4">
        <div className="flex items-end gap-2">
          <span className={'text-5xl font-bold tabular-nums ' + tone.text}>
            {currentRating}
          </span>
          <span className="mb-1 text-xs text-slate-500">{t('chart.rating.outOf')}</span>
        </div>
        <div className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-500">{t('chart.rating.ratingChange')}</span>
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
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-center py-24">
      <div className="flex flex-col items-center gap-4 text-slate-400">
        <Loader2 size={36} className="animate-spin text-emerald-500" />
        <p className="text-sm">{t('chart.loading')}</p>
      </div>
    </div>
  )
}

function ErrorState({ message, ticker }: { message: string; ticker: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center justify-center py-24">
      <div className="max-w-md rounded-xl border border-rose-500/30 bg-rose-500/10 p-6 text-center">
        <p className="font-semibold text-rose-300">
          {t('chart.failedToLoad', { ticker: ticker.toUpperCase() })}
        </p>
        <p className="mt-1 text-sm text-slate-400">{message}</p>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ChartsPage() {
  const { t } = useTranslation()
  const { ticker = 'kgh' } = useParams<{ ticker: string }>()

  // Chart bar size and time range — together they drive the interval and
  // fromDate sent to the signals endpoint. The range list depends on the bar
  // size (a 30-minute chart has no "2Y"), so the two move together below.
  const [interval, setIntervalKey] = useState<ChartInterval>(DEFAULT_INTERVAL)
  const [range, setRange] = useState<string>(DEFAULT_RANGE[DEFAULT_INTERVAL])
  const fromDate = useMemo(() => rangeFromDate(interval, range), [interval, range])
  const { data, loading, error } = useStockDetail(ticker, fromDate, interval)

  // Company fundamentals — fetched once here and shared by the Fundamentals and
  // Investment cards (both read the same payload; one fetch, not two). Volume
  // (RVOL) is fetched independently of the chart range, so it does not
  // recompute as the user scrolls/zooms the chart.
  const { data: fundamentals, loading: fundamentalsLoading } =
    useFundamentals(ticker)
  const { data: volume, loading: volumeLoading } = useTickerVolume(ticker)

  // Detection-settings state — drives which signals are shown on the chart
  // and in the strength/weakness checklist.
  const [sensitivity, setSensitivity] = useState(DEFAULT_SENSITIVITY)
  const [contextWindow, setContextWindow] = useState(DEFAULT_CONTEXT_WINDOW)

  // Tells the chart how to treat the next data swap: `true` keeps the current
  // view (seamless, for a scroll/zoom-driven range change), `false` fits the
  // new range to the view (for an explicit button click). Read by the chart
  // when the re-fetched data lands, so a ref — not state — carries it across
  // the async gap without its own re-render.
  const preserveViewRef = useRef(false)

  // Picking a range also widens the signal context window to cover it, so
  // markers appear across the whole visible chart, not just the recent part.
  const selectRange = useCallback(
    (key: string, preserveView = false) => {
      preserveViewRef.current = preserveView
      setRange(key)
      const opt = rangesFor(interval).find((r) => r.key === key)
      if (opt) setContextWindow(contextBarsFor(interval, opt.days))
    },
    [interval],
  )

  // Switching bar size also resets the range: the ranges on offer differ per
  // interval, so the one that was selected may not exist on the new one (and
  // "2Y" of 30-minute candles is not something the provider serves anyway).
  const selectInterval = useCallback((next: ChartInterval) => {
    preserveViewRef.current = false
    const nextRange = DEFAULT_RANGE[next]
    setIntervalKey(next)
    setRange(nextRange)
    const opt = rangesFor(next).find((r) => r.key === nextRange)
    if (opt) setContextWindow(contextBarsFor(next, opt.days))
  }, [])

  // Scroll-driven range switching: scrolling/zooming out past the oldest loaded
  // bar steps up to the next longer range (loading more history), and zooming
  // well inside the loaded data steps down to the next shorter one. The chart
  // refits after each step, so one scroll gesture moves at most one step and
  // the buttons stay in sync with what is on screen.
  const stepCooldown = useRef(0)

  const handleSpanSettled = useCallback(
    ({ barsBefore, visibleBars, totalBars }: VisibleSpan) => {
      if (loading || totalBars === 0) return
      if (Date.now() < stepCooldown.current) return

      const options = rangesFor(interval)
      const index = options.findIndex((r) => r.key === range)
      // Either the view runs off the left of the loaded slice, or it has been
      // zoomed out wider than the slice — both mean "show me further back".
      const wantsOlder =
        barsBefore < -PAN_PAST_START_BARS ||
        visibleBars > totalBars * ZOOM_OUT_FACTOR
      const wantsNarrower = visibleBars < totalBars * ZOOM_IN_FRACTION

      const next = wantsOlder
        ? options[index + 1]
        : wantsNarrower
          ? options[index - 1]
          : undefined
      if (!next) return

      stepCooldown.current = Date.now() + STEP_COOLDOWN_MS
      // Scroll/zoom-driven change: keep the view so the extra history slides in
      // seamlessly instead of the chart snapping to fit the new range.
      selectRange(next.key, true)
    },
    [loading, interval, range, selectRange],
  )

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

  // ── Trading-method chart overlays ───────────────────────────────────────────
  // Which methods are drawn on the chart. `null` (default) = show all. VSA's
  // markers are the built-in arrows (from `vsaSignals`); every other method's
  // markers come from `data.methodSignals`.
  const palette = useChartPalette()
  const { methods: catalogue } = useMethods()
  const [chartMethods, setChartMethods] = usePersistentState<string[] | null>(
    CHART_METHODS_KEY,
    null,
  )
  const isMethodShown = useCallback(
    (id: string) => chartMethods === null || chartMethods.includes(id),
    [chartMethods],
  )

  // Non-VSA overlay groups on this chart, each given a stable colour by its
  // backend display order (so the legend swatch and the markers always match).
  const methodGroups = useMemo(
    () =>
      (data?.methodSignals ?? []).map((g, i) => ({
        ...g,
        color: palette.methodColors[i % palette.methodColors.length],
      })),
    [data, palette],
  )

  const allChartMethodIds = useMemo(
    () => [VSA_METHOD_ID, ...methodGroups.map((g) => g.methodId)],
    [methodGroups],
  )

  const toggleChartMethod = useCallback(
    (id: string) =>
      setChartMethods((prev) => {
        const base = prev ?? allChartMethodIds
        return base.includes(id) ? base.filter((m) => m !== id) : [...base, id]
      }),
    [allChartMethodIds, setChartMethods],
  )

  // Overlays actually drawn: the selected non-VSA methods.
  const overlays = useMemo<MethodOverlay[]>(
    () =>
      methodGroups
        .filter((g) => isMethodShown(g.methodId))
        .map((g) => ({ methodId: g.methodId, color: g.color, signals: g.signals })),
    [methodGroups, isMethodShown],
  )

  // VSA arrows show only when VSA is selected (still filtered by the
  // detection-sensitivity panel, which stays a VSA-only control).
  const vsaChartSignals = useMemo(
    () => (isMethodShown(VSA_METHOD_ID) ? visibleSignals : []),
    [isMethodShown, visibleSignals],
  )

  // Legend / chooser rows: VSA first, then each overlay method.
  const legendItems = useMemo<ChartMethodLegendItem[]>(() => {
    if (!data) return []
    const vsaName = catalogue.find((m) => m.id === VSA_METHOD_ID)?.name ?? 'VSA'
    return [
      {
        id: VSA_METHOD_ID,
        name: vsaName,
        color: palette.bull,
        count: visibleSignals.length,
        selected: isMethodShown(VSA_METHOD_ID),
      },
      ...methodGroups.map((g) => ({
        id: g.methodId,
        name: g.name,
        color: g.color,
        count: g.signals.length,
        selected: isMethodShown(g.methodId),
      })),
    ]
  }, [data, catalogue, methodGroups, visibleSignals.length, isMethodShown, palette])

  if (loading && !data) return <LoadingState />
  if (error) return <ErrorState message={error} ticker={ticker} />
  if (!data) return null

  const tone = ratingTone(data.currentRating)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      {/* Asset header — pinned under the top bar (negative margins let it span
          the full width) so the company, price and rating stay in view while
          scrolling through the cards below. */}
      <div className="sticky top-0 z-30 -mx-4 -mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:-mt-6 sm:px-6">
        <CompanyPicker ticker={data.ticker} name={data.name} />
        <span className="text-xl font-semibold text-slate-200">
          {fmtPrice(data.lastPrice)} {t('common.pln')}
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
          {t('chart.vsaBadge', { rating: data.currentRating })}
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
                {data.ticker} · {intervalOption(interval).label}
                <span className="text-xs font-normal text-slate-500">
                  {intervalOption(interval).barsPerSession === 1
                    ? t('chart.sessions', { count: data.history.length })
                    : t('chart.bars', { count: data.history.length })}
                </span>
                {loading && (
                  <Loader2 size={14} className="animate-spin text-slate-500" />
                )}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <div
                  role="group"
                  aria-label={t('chart.intervalGroup')}
                  title={t('chart.intervalHint')}
                  className="flex overflow-hidden rounded-lg border border-slate-700"
                >
                  {INTERVAL_OPTIONS.map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => selectInterval(option.key)}
                      aria-pressed={interval === option.key}
                      title={t('chart.intervalTitle', { interval: option.label })}
                      className={
                        'px-2.5 py-1 text-xs font-medium transition-colors ' +
                        (interval === option.key
                          ? 'bg-slate-700 text-slate-100'
                          : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
                      }
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <div
                  role="group"
                  aria-label={t('chart.timeRangeGroup')}
                  title={t('chart.timeRangeHint')}
                  className="flex overflow-hidden rounded-lg border border-slate-700"
                >
                  {rangesFor(interval).map(({ key }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => selectRange(key)}
                      aria-pressed={range === key}
                      title={
                        key === 'MAX'
                          ? t('chart.rangeTitleMax')
                          : t('chart.rangeTitleLast', { range: key })
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
            </div>
            {/* On an intraday chart, say plainly what is different: the bars are
                fetched live (the app stores only end-of-day history, so how far
                back they go is capped), and the daily-calibrated method overlays
                are switched off rather than silently recomputed on the wrong
                bar size. The rating in the header stays the daily one. */}
            {data.intraday && (
              <p className="mb-2 px-1 text-xs text-slate-500">
                {t('chart.intradayNote', {
                  from: data.historyStart ?? '—',
                  interval: intervalOption(interval).label,
                })}
              </p>
            )}
            <ChartMethodLegend items={legendItems} onToggle={toggleChartMethod} />
            <div className="h-[300px] w-full sm:h-[420px]">
              <StockChart
                candles={data.history}
                signals={vsaChartSignals}
                overlays={overlays}
                onSpanSettled={handleSpanSettled}
                preserveViewRef={preserveViewRef}
              />
            </div>
          </Card>
          <RatingHistoryCard ticker={ticker} />
        </div>

        {/* Right: consolidated summary, volume, fundamentals / investment /
            rating / AI insight */}
        <div className="flex flex-col gap-4">
          <AnalyticsSummaryCard ticker={ticker} />
          <VolumeCard data={volume} loading={volumeLoading} />
          <FundamentalsCard
            data={fundamentals}
            loading={fundamentalsLoading}
            sector={data.sector}
          />
          <InvestmentCard data={fundamentals} loading={fundamentalsLoading} />
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
