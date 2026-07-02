// Stock detail / charts page — the "detail" half of the master–detail dashboard.
// Now backed by GET /api/stocks/{ticker}/signals via the useStockDetail hook.

import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ChevronDown, ChevronUp, Loader2, MoreHorizontal, RotateCcw } from 'lucide-react'
import { StockChart } from '../components/StockChart'
import { Card, CardTitle, InfoTip } from '../components/ui'
import { useStockDetail } from '../hooks/useStockDetail'
import type { Candle, SignalFlag, VsaSignal } from '../types'
import { deltaTone, fmtPct, fmtPrice, fmtSigned, ratingTone } from '../lib/format'

// ── Signal filtering (driven by the detection-settings panel) ─────────────────

const DEFAULT_SENSITIVITY = 60
const DEFAULT_CONTEXT_WINDOW = 120

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
      <CardTitle>Siła rynku</CardTitle>
      <ul className="px-4 pb-3">
        {strength.map((f) => (
          <SignalRow key={f.name} flag={f} />
        ))}
      </ul>
      <div className="border-t border-slate-800" />
      <CardTitle>Słabość rynku</CardTitle>
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
          <InfoTip text="Filters which VSA signals appear on the chart and in the Siła / Słabość checklist. Sensitivity: higher reveals more (and weaker) signals; lower shows only the strongest. Context window: only signals from the last N trading sessions are shown." />
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

function FundamentalsCard({ sector }: { sector: string | null }) {
  const rows = [['Sector', sector ?? '—']]
  return (
    <Card>
      <CardTitle>Dane podstawowe</CardTitle>
      <dl className="space-y-2 px-4 pb-4 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <dt className="text-slate-500">{k}</dt>
            <dd className="font-medium text-slate-200">{v}</dd>
          </div>
        ))}
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
        Ocena VSA
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
            <span className="text-slate-500">Zmiana ratingu</span>
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
  const { data, loading, error } = useStockDetail(ticker)

  // Detection-settings state — drives which signals are shown on the chart
  // and in the strength/weakness checklist.
  const [sensitivity, setSensitivity] = useState(DEFAULT_SENSITIVITY)
  const [contextWindow, setContextWindow] = useState(DEFAULT_CONTEXT_WINDOW)

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

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} ticker={ticker} />
  if (!data) return null

  const tone = ratingTone(data.currentRating)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      {/* Asset header */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 className="text-xl font-bold text-slate-100">
          {data.name ?? ticker.toUpperCase()}{' '}
          <span className="text-slate-500">({data.ticker})</span>
        </h2>
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
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-sm font-medium text-slate-300">
                {data.ticker} · 1D
              </span>
              <span className="text-xs text-slate-500">
                TradingView Lightweight Charts · {data.history.length} sessions
              </span>
            </div>
            <div className="h-[300px] w-full sm:h-[420px]">
              <StockChart candles={data.history} signals={visibleSignals} />
            </div>
          </Card>
        </div>

        {/* Right: fundamentals / rating */}
        <div className="flex flex-col gap-4">
          <FundamentalsCard sector={data.sector} />
          <RatingCard
            currentRating={data.currentRating}
            ratingChange={data.ratingChange}
          />
        </div>
      </div>
    </div>
  )
}
