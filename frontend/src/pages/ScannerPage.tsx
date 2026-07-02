// Scanner configuration page ("VSA Scanner GPW"). Three columns:
//   1. Silnik VSA — toggleable strength/weakness rules (click a rule to tune it).
//   2. Detekcja sygnału — per-signal tuning sliders, wired to shared state.
//   3. Statystyki skuteczności — effectiveness donut + sortable table.
//
// All state is lifted into ScannerPage and persisted to localStorage, so the
// engine list, the tuner, and the stats stay in sync and survive reloads.

import { useEffect, useMemo, useState } from 'react'
import { Loader2, MoreHorizontal, RotateCcw, Save } from 'lucide-react'
import { Card, CardTitle, InfoTip } from '../components/ui'
import type { EngineRule } from '../types'
import { useScannerStats } from '../hooks/useScannerStats'
import type { ApiSignalEffectiveness } from '../api/stocksApi'

/* ── Per-signal detection parameters ────────────────────────────────────── */

interface SignalParams {
  volumeSpread: number // × average spread
  priceRejection: number // %
  bgTrendStrength: number // 0–100
  minVolume: number // × average volume
  closePosition: number // % within the bar's range
  lookback: number // sessions of context
}

const DEFAULT_PARAMS: SignalParams = {
  volumeSpread: 1.5,
  priceRejection: 30,
  bgTrendStrength: 20,
  minVolume: 2.0,
  closePosition: 60,
  lookback: 20,
}

const SLIDERS: {
  key: keyof SignalParams
  label: string
  min: number
  max: number
  step: number
  suffix?: string
}[] = [
  { key: 'volumeSpread', label: 'Volume Spread', min: 0, max: 5, step: 0.1, suffix: '×' },
  { key: 'priceRejection', label: 'Price Rejection', min: 0, max: 100, step: 1, suffix: '%' },
  { key: 'bgTrendStrength', label: 'Background Trend Strength', min: 0, max: 100, step: 1 },
  { key: 'minVolume', label: 'Min Volume', min: 0, max: 5, step: 0.1, suffix: '× avg' },
  { key: 'closePosition', label: 'Close Position', min: 0, max: 100, step: 1, suffix: '%' },
  { key: 'lookback', label: 'Lookback', min: 5, max: 60, step: 1, suffix: ' sess.' },
]

/** Canonical VSA signals matching the backend SignalName enum (via SIGNAL_DISPLAY mapping). */
const ENGINE_RULES_DEFAULT: EngineRule[] = [
  { id: 'spring',   side: 'Siła',    name: 'Spring',            enabled: true  },
  { id: 'sos',      side: 'Siła',    name: 'Sign of Strength',  enabled: true  },
  { id: 'test',     side: 'Siła',    name: 'Successful Test',   enabled: true  },
  { id: 'upthrust', side: 'Słabość', name: 'Upthrust',          enabled: true  },
  { id: 'nodemand', side: 'Słabość', name: 'No Demand',         enabled: true  },
  { id: 'sow',      side: 'Słabość', name: 'Sign of Weakness',  enabled: true  },
]

const SIGNAL_NAMES = ENGINE_RULES_DEFAULT.map((r) => r.name)

/* ── Persistence ────────────────────────────────────────────────────────── */

const RULES_KEY = 'stockpilot:scanner:rules'
const PARAMS_KEY = 'stockpilot:scanner:params'

function loadRules(): EngineRule[] {
  try {
    const raw = localStorage.getItem(RULES_KEY)
    if (!raw) return ENGINE_RULES_DEFAULT
    const saved = JSON.parse(raw) as EngineRule[]
    // Merge saved enabled-state onto the canonical rule set (ignore stale ids).
    return ENGINE_RULES_DEFAULT.map(
      (r) => ({ ...r, enabled: saved.find((s) => s.id === r.id)?.enabled ?? r.enabled }),
    )
  } catch {
    return ENGINE_RULES_DEFAULT
  }
}

function buildDefaultParams(): Record<string, SignalParams> {
  return Object.fromEntries(SIGNAL_NAMES.map((n) => [n, { ...DEFAULT_PARAMS }]))
}

function loadParams(): Record<string, SignalParams> {
  try {
    const raw = localStorage.getItem(PARAMS_KEY)
    if (!raw) return buildDefaultParams()
    const saved = JSON.parse(raw) as Record<string, Partial<SignalParams>>
    const base = buildDefaultParams()
    for (const name of SIGNAL_NAMES) base[name] = { ...base[name], ...saved[name] }
    return base
  } catch {
    return buildDefaultParams()
  }
}

/* ── Left: VSA engine rule list ─────────────────────────────────────────── */

function EngineList({
  rules,
  selected,
  onToggle,
  onSelect,
  onSetAll,
}: {
  rules: EngineRule[]
  selected: string
  onToggle: (id: string) => void
  onSelect: (name: string) => void
  onSetAll: (enabled: boolean) => void
}) {
  const activeCount = rules.filter((r) => r.enabled).length
  return (
    <Card className="flex flex-col">
      <CardTitle
        right={
          <span className="text-[11px] font-medium text-slate-500">
            {activeCount}/{rules.length} active
          </span>
        }
      >
        Silnik VSA{' '}
        <InfoTip text="Turn individual VSA signals on or off. Only enabled signals count toward the effectiveness average on the right. Click a signal's name to load its detection thresholds into the tuner." />
      </CardTitle>
      <ul className="px-2 pb-2">
        {rules.map((r) => {
          const strong = r.side === 'Siła'
          const isSelected = r.name === selected
          return (
            <li key={r.id}>
              <div
                className={
                  'grid grid-cols-[auto_1fr] items-center gap-3 rounded-md px-2 py-1.5 transition-colors ' +
                  (isSelected ? 'bg-slate-800/60' : 'hover:bg-slate-800/30')
                }
              >
                <input
                  type="checkbox"
                  checked={r.enabled}
                  onChange={() => onToggle(r.id)}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-800 accent-emerald-500"
                  aria-label={`Enable ${r.name}`}
                />
                <button
                  onClick={() => onSelect(r.name)}
                  className="flex items-center gap-2 text-left text-sm"
                  title="Tune this signal"
                >
                  <span
                    className={
                      'h-2 w-2 rounded-full ' +
                      (strong ? 'bg-emerald-500' : 'bg-rose-500')
                    }
                  />
                  <span className="text-slate-500">{r.side}:</span>
                  <span
                    className={
                      (r.enabled ? 'text-slate-200' : 'text-slate-500 line-through') +
                      (isSelected ? ' font-semibold' : '')
                    }
                  >
                    {r.name}
                  </span>
                </button>
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
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  suffix?: string
  onChange: (v: number) => void
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slate-400">{label}</span>
        <span className="tabular-nums text-slate-200">
          {step < 1 ? value.toFixed(1) : value}
          {suffix ?? ''}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
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
  selected: string
  params: SignalParams
  onSelect: (name: string) => void
  onParamChange: (key: keyof SignalParams, value: number) => void
  onResetSignal: () => void
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-end gap-2">
        <div className="flex-1">
          <label className="mb-1 flex items-center gap-1.5 text-xs text-slate-500">
            Detekcja wybranego sygnału
            <InfoTip text="These thresholds control how strictly the selected signal is detected. Volume Spread and Min Volume set the required bar range and volume; Price Rejection the wick length; Close Position where the bar must close; Background Trend Strength the required prior trend; Lookback how many prior sessions of context are used." />
          </label>
          <select
            value={selected}
            onChange={(e) => onSelect(e.target.value)}
            className="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-emerald-500/50 focus:outline-none"
          >
            {SIGNAL_NAMES.map((n) => (
              <option key={n}>{n}</option>
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

      <div className="space-y-4">
        {SLIDERS.map((s) => (
          <Slider
            key={s.key}
            label={s.label}
            value={params[s.key]}
            min={s.min}
            max={s.max}
            step={s.step}
            suffix={s.suffix}
            onChange={(v) => onParamChange(s.key, v)}
          />
        ))}
      </div>

      {/* Visual aid — reacts (lightly) to the current parameters */}
      <div className="mt-5">
        <p className="mb-1 text-sm text-slate-400">Visual aid</p>
        <p className="mb-3 text-xs text-slate-500">
          Preview of how <span className="text-slate-300">{selected}</span> is
          detected with the current parameters.
        </p>
        <div className="grid grid-cols-[1fr_auto] items-center gap-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <MiniCandles
            rejection={params.priceRejection}
            closePosition={params.closePosition}
          />
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between gap-4">
              <span className="text-slate-500">Volume threshold</span>
              <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 tabular-nums text-slate-200">
                {params.minVolume.toFixed(1)}× avg
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

/** Mini candlestick cluster; wick length scales with the rejection setting. */
function MiniCandles({
  rejection,
  closePosition,
}: {
  rejection: number
  closePosition: number
}) {
  const wick = 4 + (rejection / 100) * 20 // longer wick = more rejection
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
              y1={b.y - wick}
              y2={b.y + b.h + wick}
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
        <div className="text-xs text-slate-500">Zysk</div>
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
  error,
}: {
  enabledNames: Set<string>
  selected: string
  onSelect: (name: string) => void
  stats: ApiSignalEffectiveness[]
  loading: boolean
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

  if (loading) {
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
    <Card className="flex flex-col">
      <CardTitle right={<MoreHorizontal size={16} className="text-slate-600" />}>
        Statystyki skuteczności{' '}
        <InfoTip
          align="right"
          text="Historical hit-rate and reward/risk for each VSA signal on the GPW, from a 10-session back-test over the last 120 sessions. The donut shows the average success rate across your enabled signals. Skut.% = success rate, Z/R = reward-to-risk, Trans. = number of occurrences."
        />
      </CardTitle>

      <div className="px-4 pb-2">
        <EffectivenessDonut profit={avg} />
        <div className="mt-2 flex justify-center gap-5 text-xs">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Zysk {avg}%
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-slate-700" /> Strata{' '}
            {100 - avg}%
          </span>
        </div>
        <p className="mt-2 text-center text-[11px] text-slate-500">
          10-session back-test · last 120 sessions
        </p>
      </div>

      <table className="w-full px-2 pb-4 text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
            <th
              className="cursor-pointer select-none px-4 py-2 font-medium hover:text-slate-300"
              onClick={() => toggleSort('signal')}
            >
              Sygnał{arrow('signal')}
            </th>
            <th
              className="cursor-pointer select-none px-2 py-2 text-right font-medium hover:text-slate-300"
              onClick={() => toggleSort('successPct')}
            >
              Skut.%{arrow('successPct')}
            </th>
            <th
              className="cursor-pointer select-none px-2 py-2 text-right font-medium hover:text-slate-300"
              onClick={() => toggleSort('rewardRisk')}
            >
              Z/R{arrow('rewardRisk')}
            </th>
            <th
              className="cursor-pointer select-none px-4 py-2 text-right font-medium hover:text-slate-300"
              onClick={() => toggleSort('count')}
            >
              Trans.{arrow('count')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const on = enabledNames.has(r.signal)
            const isSel = r.signal === selected
            return (
              <tr
                key={r.signal}
                onClick={() => onSelect(r.signal)}
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

export function ScannerPage() {
  const { data: statsData, loading: statsLoading, error: statsError } = useScannerStats()
  const [rules, setRules] = useState<EngineRule[]>(loadRules)
  const [paramsBySignal, setParamsBySignal] =
    useState<Record<string, SignalParams>>(loadParams)
  const [selected, setSelected] = useState<string>(
    () => rules.find((r) => r.enabled)?.name ?? SIGNAL_NAMES[0],
  )
  const [savedAt, setSavedAt] = useState<number | null>(null)

  // Persist rules + params whenever they change.
  useEffect(() => {
    try {
      localStorage.setItem(RULES_KEY, JSON.stringify(rules))
      localStorage.setItem(PARAMS_KEY, JSON.stringify(paramsBySignal))
    } catch {
      /* ignore */
    }
  }, [rules, paramsBySignal])

  const enabledNames = useMemo(
    () => new Set(rules.filter((r) => r.enabled).map((r) => r.name)),
    [rules],
  )

  const toggleRule = (id: string) =>
    setRules((p) => p.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)))

  const setAllRules = (enabled: boolean) =>
    setRules((p) => p.map((r) => ({ ...r, enabled })))

  const setParam = (key: keyof SignalParams, value: number) =>
    setParamsBySignal((p) => ({
      ...p,
      [selected]: { ...p[selected], [key]: value },
    }))

  const resetSignal = () =>
    setParamsBySignal((p) => ({ ...p, [selected]: { ...DEFAULT_PARAMS } }))

  const resetAll = () => {
    setRules(ENGINE_RULES_DEFAULT)
    setParamsBySignal(buildDefaultParams())
    setSelected(ENGINE_RULES_DEFAULT.find((r) => r.enabled)?.name ?? SIGNAL_NAMES[0])
  }

  const saveNow = () => {
    try {
      localStorage.setItem(RULES_KEY, JSON.stringify(rules))
      localStorage.setItem(PARAMS_KEY, JSON.stringify(paramsBySignal))
      setSavedAt(Date.now())
    } catch {
      /* ignore */
    }
  }

  // Clear the "Saved ✓" flash after 2 s (cleaned up on unmount / re-save).
  useEffect(() => {
    if (savedAt == null) return
    const t = setTimeout(() => setSavedAt(null), 2000)
    return () => clearTimeout(t)
  }, [savedAt])

  return (
    <div className="p-4 sm:p-6">
      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">VSA Engine</h2>
          <p className="text-sm text-slate-500">
            {enabledNames.size} of {rules.length} signals active · settings
            auto-saved
          </p>
        </div>
        <div className="flex items-center gap-2">
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

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
        <EngineList
          rules={rules}
          selected={selected}
          onToggle={toggleRule}
          onSelect={setSelected}
          onSetAll={setAllRules}
        />
        <SignalTuner
          selected={selected}
          params={paramsBySignal[selected] ?? DEFAULT_PARAMS}
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
          error={statsError}
        />
      </div>
    </div>
  )
}
