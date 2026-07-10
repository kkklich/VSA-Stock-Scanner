// Scanner configuration page ("VSA Scanner GPW"). Three columns:
//   1. VSA Engine — toggleable strength/weakness rules (click a rule to tune it).
//   2. Selected signal — per-signal tuning sliders.
//   3. Effectiveness — effectiveness donut + sortable table.
//
// These settings are THE live engine configuration: they are persisted to
// localStorage and sent to the backend with every ranking / chart / stats
// request, so changing a slider here changes what the whole app detects.
// The stats column re-runs the back-test (debounced) as you tune.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, MoreHorizontal, RotateCcw, Save } from 'lucide-react'
import { Card, CardTitle, InfoTip } from '../components/ui'
import { useScannerStats } from '../hooks/useScannerStats'
import type { ApiSignalEffectiveness } from '../api/stocksApi'
import {
  HORIZON_IDS,
  SIGNAL_DEFAULTS,
  SIGNAL_IDS,
  loadVsaSettings,
  matchHorizon,
  presetSettings,
  saveVsaSettings,
  settingsQueryValue,
  type HorizonId,
  type SignalId,
  type SignalSettings,
  type VsaSettings,
} from '../lib/vsaSettings'

/* ── Signal metadata ────────────────────────────────────────────────────── */

const SIGNAL_META: Record<
  SignalId,
  { name: string; side: 'Strength' | 'Weakness'; blurb: string }
> = {
  spring: {
    name: 'Spring',
    side: 'Strength',
    blurb:
      'Price breaks below recent support but closes back above it — sellers were trapped. Valid on high volume (absorption) or very low volume (no supply).',
  },
  sos: {
    name: 'Sign of Strength',
    side: 'Strength',
    blurb:
      'A wide up-bar on high volume closing near its high — professional buying pushing the price up.',
  },
  test: {
    name: 'Successful Test',
    side: 'Strength',
    blurb:
      'A dip below the previous low that finds no sellers: very low volume and a close near the high. Confirms earlier strength.',
  },
  upthrust: {
    name: 'Upthrust',
    side: 'Weakness',
    blurb:
      'Price spikes above recent resistance but closes back below it near the low — buyers were trapped. Valid on high or unusually low volume.',
  },
  nodemand: {
    name: 'No Demand',
    side: 'Weakness',
    blurb:
      'A narrow up-bar on very low volume — professionals are not interested in higher prices.',
  },
  sow: {
    name: 'Sign of Weakness',
    side: 'Weakness',
    blurb:
      'A wide down-bar on high volume closing near its low — professional selling pressing the price down.',
  },
}

const NAME_TO_ID: Record<string, SignalId> = Object.fromEntries(
  SIGNAL_IDS.map((id) => [SIGNAL_META[id].name, id]),
) as Record<string, SignalId>

/* ── Horizon presets ────────────────────────────────────────────────────── */

const HORIZON_META: Record<HorizonId, { label: string; hint: string }> = {
  short: {
    label: 'Short',
    hint:
      'Short term (swing, days–2 weeks): 10-session context — signals react to local support/resistance, more of them, quicker but noisier.',
  },
  mid: {
    label: 'Mid',
    hint:
      'Mid term (weeks–2 months): 20-session context — the standard engine defaults.',
  },
  long: {
    label: 'Long',
    hint:
      'Long term (position, months+): 40-session context with stricter volume/spread thresholds — only the strongest signals qualify.',
  },
}

/* ── Per-signal slider metadata ─────────────────────────────────────────── */

interface SliderDef {
  key: keyof Omit<SignalSettings, 'enabled'>
  label: string
  min: number
  max: number
  step: number
  suffix: string
  help: string
}

// High-volume signals require volume ABOVE avg × volMult; quiet signals
// require volume BELOW avg × volMult. Same idea for the spread multiplier.
const QUIET_SIGNALS: SignalId[] = ['test', 'nodemand']
const BULLISH_SIGNALS: SignalId[] = ['spring', 'sos', 'test']

function slidersFor(id: SignalId): SliderDef[] {
  const quiet = QUIET_SIGNALS.includes(id)
  const bullish = BULLISH_SIGNALS.includes(id)
  const defs: SliderDef[] = []

  // Successful Test has no spread requirement; No Demand needs a NARROW bar.
  if (id !== 'test') {
    defs.push({
      key: 'spreadMult',
      label: id === 'nodemand' ? 'Max spread' : 'Min spread',
      min: 0.1,
      max: 5,
      step: 0.1,
      suffix: '× avg',
      help:
        id === 'nodemand'
          ? 'The bar must be NARROWER than the average bar times this value.'
          : 'The bar must be WIDER than the average bar times this value. Lower = more signals.',
    })
  }

  defs.push({
    key: 'volMult',
    label: quiet ? 'Max volume' : 'Min volume',
    min: 0.1,
    max: 5,
    step: 0.1,
    suffix: '× avg',
    help: quiet
      ? 'Volume must stay BELOW the average times this value — these signals need quiet trading.'
      : 'Volume must exceed the average times this value. Lower = more signals.',
  })

  defs.push({
    key: 'closePos',
    label: bullish ? 'Min close position' : 'Max close position',
    min: 0,
    max: 100,
    step: 1,
    suffix: '%',
    help: bullish
      ? 'Where the close must sit in the bar (0% = low, 100% = high). Bullish bars must close high.'
      : 'Bearish bars must close low — the close must stay below this position in the bar.',
  })

  defs.push({
    key: 'lookback',
    label: 'Lookback',
    min: 5,
    max: 60,
    step: 1,
    suffix: ' sess.',
    help:
      'How many previous sessions define "average" volume/spread and the support/resistance levels.',
  })

  return defs
}

/* ── Left: VSA engine rule list ─────────────────────────────────────────── */

function EngineList({
  settings,
  selected,
  onToggle,
  onSelect,
  onSetAll,
}: {
  settings: VsaSettings
  selected: SignalId
  onToggle: (id: SignalId) => void
  onSelect: (id: SignalId) => void
  onSetAll: (enabled: boolean) => void
}) {
  const activeCount = SIGNAL_IDS.filter((id) => settings[id].enabled).length
  return (
    <Card className="flex flex-col">
      <CardTitle
        right={
          <span className="text-[11px] font-medium text-slate-500">
            {activeCount}/{SIGNAL_IDS.length} active
          </span>
        }
      >
        VSA Engine{' '}
        <InfoTip text="Turn individual VSA signals on or off. Disabled signals disappear everywhere: the ranking, the charts and the stats. Click a signal's name to load its detection thresholds into the tuner." />
      </CardTitle>
      <ul className="px-2 pb-2">
        {SIGNAL_IDS.map((id) => {
          const meta = SIGNAL_META[id]
          const enabled = settings[id].enabled
          const strong = meta.side === 'Strength'
          const isSelected = id === selected
          return (
            <li key={id}>
              <div
                className={
                  'grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-md px-2 py-1.5 transition-colors ' +
                  (isSelected ? 'bg-slate-800/60' : 'hover:bg-slate-800/30')
                }
              >
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={() => onToggle(id)}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-800 accent-emerald-500"
                  aria-label={`Enable ${meta.name}`}
                />
                <button
                  onClick={() => onSelect(id)}
                  className="flex items-center gap-2 text-left text-sm"
                  title="Tune this signal"
                >
                  <span
                    className={
                      'h-2 w-2 rounded-full ' +
                      (strong ? 'bg-emerald-500' : 'bg-rose-500')
                    }
                  />
                  <span className="text-slate-500">{meta.side}:</span>
                  <span
                    className={
                      (enabled ? 'text-slate-200' : 'text-slate-500 line-through') +
                      (isSelected ? ' font-semibold' : '')
                    }
                  >
                    {meta.name}
                  </span>
                </button>
                <InfoTip align="right" text={meta.blurb} />
              </div>
            </li>
          )
        })}
      </ul>
      <div className="flex gap-2 border-t border-slate-800 px-3 py-2 text-xs">
        <button
          onClick={() => onSetAll(true)}
          className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          Enable all
        </button>
        <button
          onClick={() => onSetAll(false)}
          className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          Disable all
        </button>
      </div>
    </Card>
  )
}

/* ── Center: signal tuner ───────────────────────────────────────────────── */

function Slider({
  def,
  value,
  onChange,
}: {
  def: SliderDef
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 text-slate-400">
          {def.label}
          <InfoTip text={def.help} />
        </span>
        <span className="tabular-nums text-slate-200">
          {def.step < 1 ? value.toFixed(1) : value}
          {def.suffix}
        </span>
      </div>
      <input
        type="range"
        min={def.min}
        max={def.max}
        step={def.step}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
        className="w-full accent-emerald-500"
      />
    </div>
  )
}

function SignalTuner({
  selected,
  params,
  onSelect,
  onParamChange,
  onResetSignal,
}: {
  selected: SignalId
  params: SignalSettings
  onSelect: (id: SignalId) => void
  onParamChange: (key: keyof SignalSettings, value: number) => void
  onResetSignal: () => void
}) {
  const meta = SIGNAL_META[selected]
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-end gap-2">
        <div className="flex-1">
          <label className="mb-1 flex items-center gap-1.5 text-xs text-slate-500">
            Selected signal
            <InfoTip text="These thresholds control how strictly the selected signal is detected — they are sent to the backend and change the real calculation everywhere in the app. Tighter thresholds = fewer but cleaner signals; looser = more but noisier." />
          </label>
          <select
            value={selected}
            onChange={(e) => onSelect(e.target.value as SignalId)}
            className="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-emerald-500/50 focus:outline-none"
          >
            {SIGNAL_IDS.map((id) => (
              <option key={id} value={id}>
                {SIGNAL_META[id].name}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={onResetSignal}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
          title="Reset this signal to defaults"
        >
          <RotateCcw size={14} /> Reset
        </button>
      </div>

      <p className="mb-4 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-xs leading-relaxed text-slate-400">
        {meta.blurb}
      </p>

      <div className="space-y-4">
        {slidersFor(selected).map((def) => (
          <Slider
            key={def.key}
            def={def}
            value={params[def.key]}
            onChange={(v) => onParamChange(def.key, v)}
          />
        ))}
      </div>

      {/* Visual aid — reacts (lightly) to the current parameters */}
      <div className="mt-5">
        <p className="mb-1 text-sm text-slate-400">Visual aid</p>
        <p className="mb-3 text-xs text-slate-500">
          Preview of how <span className="text-slate-300">{meta.name}</span> is
          detected with the current parameters.
        </p>
        <div className="grid grid-cols-[1fr_auto] items-center gap-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <MiniCandles closePosition={params.closePos} />
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between gap-4">
              <span className="text-slate-500">Volume threshold</span>
              <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 tabular-nums text-slate-200">
                {params.volMult.toFixed(1)}× avg
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-slate-500">Lookback</span>
              <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 tabular-nums text-slate-200">
                {params.lookback} sess.
              </span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

/** Mini candlestick cluster; the close marker follows the close-position setting. */
function MiniCandles({ closePosition }: { closePosition: number }) {
  const bars = [
    { up: false, h: 26, y: 14 },
    { up: false, h: 34, y: 8 },
    { up: true, h: 22, y: 22 },
    { up: true, h: 30, y: 12 },
    { up: false, h: 18, y: 26 },
    { up: true, h: 36, y: 6 },
    { up: true, h: 24, y: 18 },
  ]
  return (
    <svg width="150" height="72" className="overflow-visible">
      {bars.map((b, i) => {
        const x = 8 + i * 20
        const color = b.up ? '#10B981' : '#F43F5E'
        // Close marker position within the bar, driven by closePosition %.
        const closeY = b.y + b.h * (1 - closePosition / 100)
        return (
          <g key={i}>
            <line
              x1={x}
              x2={x}
              y1={b.y - 6}
              y2={b.y + b.h + 6}
              stroke={color}
              strokeWidth={1}
            />
            <rect x={x - 5} y={b.y} width={10} height={b.h} fill={color} rx={1} />
            <line
              x1={x - 6}
              x2={x + 6}
              y1={closeY}
              y2={closeY}
              stroke="#e2e8f0"
              strokeWidth={1}
              opacity={0.5}
            />
          </g>
        )
      })}
    </svg>
  )
}

/* ── Right: effectiveness statistics ────────────────────────────────────── */

function EffectivenessDonut({ profit }: { profit: number }) {
  const r = 52
  const c = 2 * Math.PI * r
  const profitLen = (profit / 100) * c
  return (
    <div className="relative grid place-items-center">
      <svg width="160" height="160" viewBox="0 0 160 160">
        <circle cx="80" cy="80" r={r} fill="none" stroke="#1e293b" strokeWidth="18" />
        <circle
          cx="80"
          cy="80"
          r={r}
          fill="none"
          stroke="#10B981"
          strokeWidth="18"
          strokeDasharray={`${profitLen} ${c - profitLen}`}
          strokeDashoffset={c / 4}
          transform="rotate(-90 80 80)"
          strokeLinecap="butt"
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-bold text-emerald-400">{profit}%</div>
        <div className="text-xs text-slate-500">Win</div>
      </div>
    </div>
  )
}

type SortKey = 'signal' | 'successPct' | 'rewardRisk' | 'count'

function EffectivenessStats({
  enabledNames,
  selected,
  onSelect,
  stats,
  loading,
  refreshing,
  error,
}: {
  enabledNames: Set<string>
  selected: SignalId
  onSelect: (id: SignalId) => void
  stats: ApiSignalEffectiveness[]
  loading: boolean
  refreshing: boolean
  error: string | null
}) {
  const [sortKey, setSortKey] = useState<SortKey>('successPct')
  const [asc, setAsc] = useState(false)

  const avg = useMemo(() => {
    const active = stats.filter((r) => enabledNames.has(r.signal))
    if (active.length === 0) return 0
    return Math.round(
      active.reduce((a, r) => a + r.successPct, 0) / active.length,
    )
  }, [stats, enabledNames])

  const sorted = useMemo(() => {
    const rows = [...stats]
    rows.sort((a, b) => {
      const av = a[sortKey as keyof ApiSignalEffectiveness]
      const bv = b[sortKey as keyof ApiSignalEffectiveness]
      const cmp =
        typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv))
      return asc ? cmp : -cmp
    })
    return rows
  }, [stats, sortKey, asc])

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setAsc((v) => !v)
    else {
      setSortKey(key)
      setAsc(false)
    }
  }

  const arrow = (key: SortKey) =>
    key === sortKey ? (asc ? ' ▲' : ' ▼') : ''

  if (loading && stats.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400">
        <Loader2 size={28} className="animate-spin text-emerald-500" />
        <p className="text-sm">Computing back-test stats…</p>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="flex flex-col items-center justify-center py-12 gap-2 text-slate-400">
        <p className="text-sm text-rose-400">Stats unavailable</p>
        <p className="text-xs text-slate-500">{error}</p>
      </Card>
    )
  }

  return (
    <Card className={'flex flex-col transition-opacity ' + (refreshing ? 'opacity-60' : '')}>
      <CardTitle
        right={
          refreshing ? (
            <Loader2 size={14} className="animate-spin text-emerald-500" />
          ) : (
            <MoreHorizontal size={16} className="text-slate-600" />
          )
        }
      >
        Effectiveness{' '}
        <InfoTip
          align="right"
          text="Historical hit-rate and reward/risk for each VSA signal on the GPW, from a 10-session back-test over the last 120 sessions — recomputed with YOUR current thresholds. The donut shows the average success rate across your enabled signals. Success% = success rate, R/R = reward-to-risk, Trades = number of occurrences."
        />
      </CardTitle>

      <div className="px-4 pb-2">
        <EffectivenessDonut profit={avg} />
        <div className="mt-2 flex justify-center gap-5 text-xs">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Win {avg}%
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-slate-700" /> Loss{' '}
            {100 - avg}%
          </span>
        </div>
        <p className="mt-2 text-center text-[11px] text-slate-500">
          10-session back-test · last 120 sessions · your settings
        </p>
      </div>

      <table className="w-full px-2 pb-4 text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
            <th
              className="cursor-pointer select-none px-4 py-2 font-medium hover:text-slate-300"
              onClick={() => toggleSort('signal')}
            >
              Signal{arrow('signal')}
            </th>
            <th
              className="cursor-pointer select-none px-2 py-2 text-right font-medium hover:text-slate-300"
              onClick={() => toggleSort('successPct')}
            >
              Success%{arrow('successPct')}
            </th>
            <th
              className="cursor-pointer select-none px-2 py-2 text-right font-medium hover:text-slate-300"
              onClick={() => toggleSort('rewardRisk')}
            >
              R/R{arrow('rewardRisk')}
            </th>
            <th
              className="cursor-pointer select-none px-4 py-2 text-right font-medium hover:text-slate-300"
              onClick={() => toggleSort('count')}
            >
              Trades{arrow('count')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const on = enabledNames.has(r.signal)
            const isSel = NAME_TO_ID[r.signal] === selected
            return (
              <tr
                key={r.signal}
                onClick={() => {
                  const id = NAME_TO_ID[r.signal]
                  if (id) onSelect(id)
                }}
                className={
                  'cursor-pointer border-t border-slate-800/60 transition-colors ' +
                  (isSel ? 'bg-slate-800/50 ' : 'hover:bg-slate-800/30 ') +
                  (on ? '' : 'opacity-40')
                }
                title={on ? 'Tune this signal' : 'Signal disabled'}
              >
                <td className="px-4 py-2 text-slate-200">{r.signal}</td>
                <td className="px-2 py-2 text-right tabular-nums text-slate-300">
                  {r.count > 0 ? `${r.successPct}%` : '—'}
                </td>
                <td
                  className={
                    'px-2 py-2 text-right tabular-nums ' +
                    (r.rewardRisk >= 1 ? 'text-emerald-400' : r.rewardRisk > 0 ? 'text-rose-400' : 'text-slate-500')
                  }
                >
                  {r.count > 0 ? r.rewardRisk.toFixed(1) : '—'}
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                  {r.count}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Card>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

const STATS_DEBOUNCE_MS = 800

export function ScannerPage() {
  const [settings, setSettings] = useState<VsaSettings>(loadVsaSettings)
  const [selected, setSelected] = useState<SignalId>(
    () => SIGNAL_IDS.find((id) => loadVsaSettings()[id].enabled) ?? 'spring',
  )
  const [savedAt, setSavedAt] = useState<number | null>(null)

  // Debounced serialized settings — drives the back-test stats refetch so
  // dragging a slider doesn't fire a request per pixel.
  const [debouncedQuery, setDebouncedQuery] = useState<string | undefined>(
    () => settingsQueryValue(loadVsaSettings()),
  )
  const isFirstRender = useRef(true)

  useEffect(() => {
    saveVsaSettings(settings)
    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }
    const t = setTimeout(
      () => setDebouncedQuery(settingsQueryValue(settings)),
      STATS_DEBOUNCE_MS,
    )
    return () => clearTimeout(t)
  }, [settings])

  const {
    data: statsData,
    loading: statsLoading,
    error: statsError,
  } = useScannerStats(debouncedQuery)

  const enabledNames = useMemo(
    () =>
      new Set(
        SIGNAL_IDS.filter((id) => settings[id].enabled).map(
          (id) => SIGNAL_META[id].name,
        ),
      ),
    [settings],
  )

  const toggleSignal = (id: SignalId) =>
    setSettings((p) => ({ ...p, [id]: { ...p[id], enabled: !p[id].enabled } }))

  const setAllSignals = (enabled: boolean) =>
    setSettings(
      (p) =>
        Object.fromEntries(
          SIGNAL_IDS.map((id) => [id, { ...p[id], enabled }]),
        ) as VsaSettings,
    )

  const setParam = (key: keyof SignalSettings, value: number) =>
    setSettings((p) => ({
      ...p,
      [selected]: { ...p[selected], [key]: value },
    }))

  const resetSignal = () =>
    setSettings((p) => ({ ...p, [selected]: { ...SIGNAL_DEFAULTS[selected] } }))

  const resetAll = () => {
    setSettings(
      Object.fromEntries(
        SIGNAL_IDS.map((id) => [id, { ...SIGNAL_DEFAULTS[id] }]),
      ) as VsaSettings,
    )
    setSelected('spring')
  }

  const applyHorizon = (h: HorizonId) => setSettings(presetSettings(h))
  const activeHorizon = useMemo(() => matchHorizon(settings), [settings])

  const saveNow = () => {
    saveVsaSettings(settings)
    setSavedAt(Date.now())
  }

  // Clear the "Saved ✓" flash after 2 s (cleaned up on unmount / re-save).
  useEffect(() => {
    if (savedAt == null) return
    const t = setTimeout(() => setSavedAt(null), 2000)
    return () => clearTimeout(t)
  }, [savedAt])

  const enabledCount = SIGNAL_IDS.filter((id) => settings[id].enabled).length

  return (
    <div className="p-4 sm:p-6">
      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-1.5 text-lg font-semibold text-slate-100">
            VSA Engine
            <InfoTip text="This is the live configuration of the VSA engine. Everything you change here is applied to the real calculation: the Dashboard ranking, the Watchlist, the chart markers and the stats on the right all use these thresholds." />
          </h2>
          <p className="text-sm text-slate-500">
            {enabledCount} of {SIGNAL_IDS.length} signals active · applies to the
            whole app · auto-saved
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1 text-xs text-slate-500">
            Horizon
            <InfoTip text="One-click default settings per investment horizon. Short = 10-session lookback (swing), Mid = 20 sessions (the app defaults), Long = 40 sessions with stricter thresholds (position trading). Applies to the whole app; you can still fine-tune any slider afterwards." />
          </span>
          <div
            role="group"
            aria-label="Investment horizon"
            className="flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5"
          >
            {HORIZON_IDS.map((h) => (
              <button
                key={h}
                onClick={() => applyHorizon(h)}
                title={HORIZON_META[h].hint}
                className={
                  'rounded-md px-2.5 py-1.5 text-sm transition-colors ' +
                  (activeHorizon === h
                    ? 'bg-emerald-600 font-medium text-white'
                    : 'text-slate-400 hover:text-slate-200')
                }
              >
                {HORIZON_META[h].label}
              </button>
            ))}
          </div>
          {savedAt && (
            <span className="text-xs text-emerald-400">Saved ✓</span>
          )}
          <button
            onClick={saveNow}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          >
            <Save size={14} /> Save
          </button>
          <button
            onClick={resetAll}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            <RotateCcw size={14} /> Reset all
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)_360px]">
        <EngineList
          settings={settings}
          selected={selected}
          onToggle={toggleSignal}
          onSelect={setSelected}
          onSetAll={setAllSignals}
        />
        <SignalTuner
          selected={selected}
          params={settings[selected]}
          onSelect={setSelected}
          onParamChange={setParam}
          onResetSignal={resetSignal}
        />
        <EffectivenessStats
          enabledNames={enabledNames}
          selected={selected}
          onSelect={setSelected}
          stats={statsData ?? []}
          loading={statsLoading}
          refreshing={statsLoading && (statsData?.length ?? 0) > 0}
          error={statsError}
        />
      </div>
    </div>
  )
}
