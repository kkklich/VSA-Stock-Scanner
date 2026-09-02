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
import type { ApiFundamentals } from '../api/stocksApi'
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

// ── Trading-method chart overlays ─────────────────────────────────────────────

/** Method id whose overlay is the built-in VSA arrows (from `vsaSignals`). */
const VSA_METHOD_ID = 'vsa'
/** VSA's marker/legend colour (emerald = strength, matching the arrows). */
const VSA_COLOR = '#10B981'
/**
 * Distinct marker colours for the OTHER methods, assigned in backend display
 * order. Chosen to read clearly on dark candlesticks and stay apart from the
 * emerald/rose VSA arrows.
 */
const OVERLAY_COLORS = [
  '#F59E0B', // amber
  '#6366F1', // indigo
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#A855F7', // purple
  '#84CC16', // lime
] as const

/** localStorage key for which methods are drawn on the stock chart. */
const CHART_METHODS_KEY = 'stockpilot:chart-methods:v1'

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

            {data?.website && (
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">{t('chart.fundamentals.www')}</dt>
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

  // Chart time range — drives the fromDate sent to the signals endpoint.
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE)
  const fromDate = useMemo(() => rangeFromDate(range), [range])
  const { data, loading, error } = useStockDetail(ticker, fromDate)

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
  const selectRange = useCallback((key: RangeKey, preserveView = false) => {
    preserveViewRef.current = preserveView
    setRange(key)
    const opt = RANGE_OPTIONS.find((r) => r.key === key)
    if (opt) setContextWindow(opt.sessions)
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

      // eslint-disable-next-line no-console
      console.log('[span]', range, 'before=' + barsBefore.toFixed(1), 'vis=' + visibleBars.toFixed(1), 'total=' + totalBars)
      const index = RANGE_OPTIONS.findIndex((r) => r.key === range)
      // Either the view runs off the left of the loaded slice, or it has been
      // zoomed out wider than the slice — both mean "show me further back".
      const wantsOlder =
        barsBefore < -PAN_PAST_START_BARS ||
        visibleBars > totalBars * ZOOM_OUT_FACTOR
      const wantsNarrower = visibleBars < totalBars * ZOOM_IN_FRACTION

      const next = wantsOlder
        ? RANGE_OPTIONS[index + 1]
        : wantsNarrower
          ? RANGE_OPTIONS[index - 1]
          : undefined
      if (!next) return

      stepCooldown.current = Date.now() + STEP_COOLDOWN_MS
      // Scroll/zoom-driven change: keep the view so the extra history slides in
      // seamlessly instead of the chart snapping to fit the new range.
      selectRange(next.key, true)
    },
    [loading, range, selectRange],
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
        color: OVERLAY_COLORS[i % OVERLAY_COLORS.length],
      })),
    [data],
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
        color: VSA_COLOR,
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
  }, [data, catalogue, methodGroups, visibleSignals.length, isMethodShown])

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
                {data.ticker} · 1D
                <span className="text-xs font-normal text-slate-500">
                  {t('chart.sessions', { count: data.history.length })}
                </span>
                {loading && (
                  <Loader2 size={14} className="animate-spin text-slate-500" />
                )}
              </span>
              <div
                role="group"
                aria-label={t('chart.timeRangeGroup')}
                title={t('chart.timeRangeHint')}
                className="flex overflow-hidden rounded-lg border border-slate-700"
              >
                {RANGE_OPTIONS.map(({ key }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => selectRange(key)}
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
