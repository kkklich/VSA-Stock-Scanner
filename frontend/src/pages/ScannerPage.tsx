// Scanner configuration page ("VSA Scanner GPW"). Three columns:
//   1. Silnik VSA — toggleable strength/weakness rules.
//   2. Detekcja sygnału — per-signal tuning sliders + visual aid.
//   3. Statystyki skuteczności — effectiveness donut + table.

import { useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import { Card, CardTitle } from '../components/ui'
import { mockEffectiveness, mockEngineRules } from '../data/mockData'
import type { EngineRule } from '../types'

/* ── Left: VSA engine rule list ─────────────────────────────────────────── */

function EngineList() {
  const [rules, setRules] = useState<EngineRule[]>(mockEngineRules)
  const toggle = (id: string) =>
    setRules((p) =>
      p.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r))
    )
  return (
    <Card className="flex flex-col">
      <CardTitle>Silnik VSA</CardTitle>
      <ul className="px-2 pb-3">
        <li className="grid grid-cols-[auto_1fr] gap-3 px-2 pb-2 text-[11px] uppercase tracking-wider text-slate-500">
          <span className="w-4" />
          <span>Sygnał</span>
        </li>
        {rules.map((r) => {
          const strong = r.side === 'Siła'
          return (
            <li
              key={r.id}
              className="grid grid-cols-[auto_1fr] items-center gap-3 rounded-md px-2 py-1.5 hover:bg-slate-800/30"
            >
              <input
                type="checkbox"
                checked={r.enabled}
                onChange={() => toggle(r.id)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-800 accent-emerald-500"
              />
              <span className="flex items-center gap-2 text-sm">
                <span
                  className={
                    'h-2 w-2 rounded-full ' +
                    (strong ? 'bg-emerald-500' : 'bg-rose-500')
                  }
                />
                <span className="text-slate-500">{r.side}:</span>
                <span className="text-slate-200">{r.name}</span>
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

/* ── Center: signal tuner ───────────────────────────────────────────────── */

function Slider({
  label,
  value,
  min,
  max,
  step = 1,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
}) {
  const [v, setV] = useState(value)
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slate-400">{label}</span>
        <span className="tabular-nums text-slate-200">{v}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        onChange={(e) => setV(+e.target.value)}
        className="w-full accent-emerald-500"
      />
    </div>
  )
}

function SignalTuner() {
  return (
    <Card className="p-5">
      <div className="mb-4">
        <label className="mb-1 block text-xs text-slate-500">
          Detekcja wybranego sygnału
        </label>
        <select className="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-emerald-500/50 focus:outline-none">
          <option>Spring</option>
          <option>Upthrust</option>
          <option>No Demand</option>
          <option>Sign of Strength</option>
          <option>Test</option>
        </select>
      </div>

      <div className="space-y-4">
        <Slider label="Volume Spread" value={1.5} min={0} max={5} step={0.1} />
        <Slider label="Price Rejection %" value={30} min={0} max={100} />
        <Slider label="Background Trend Strength" value={20} min={0} max={100} />
        <Slider label="Volume Threshold" value={0} min={0} max={100} />
      </div>

      {/* Visual aid mini preview */}
      <div className="mt-5">
        <p className="mb-1 text-sm text-slate-400">Visual aid</p>
        <p className="mb-3 text-xs text-slate-500">
          Adjust the parameters above to see how the detector reacts.
        </p>
        <div className="grid grid-cols-[1fr_auto] items-center gap-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <MiniCandles />
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between gap-4">
              <span className="text-slate-500">Context window</span>
              <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-slate-200">
                10
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-slate-500">Lookback (sessions)</span>
              <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-slate-200">
                2026
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 space-y-4">
        <Slider label="Context Rejection %" value={5} min={0} max={100} />
        <Slider label="Background Trend Strength" value={42} min={0} max={100} />
      </div>
    </Card>
  )
}

/** Decorative mini candlestick cluster for the visual-aid box. */
function MiniCandles() {
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
    <svg width="150" height="64" className="overflow-visible">
      {bars.map((b, i) => {
        const x = 8 + i * 20
        const color = b.up ? '#10B981' : '#F43F5E'
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={b.y - 5} y2={b.y + b.h + 5} stroke={color} strokeWidth={1} />
            <rect x={x - 5} y={b.y} width={10} height={b.h} fill={color} rx={1} />
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

function EffectivenessStats() {
  const avg = Math.round(
    mockEffectiveness.reduce((a, r) => a + r.successPct, 0) /
      mockEffectiveness.length
  )
  return (
    <Card className="flex flex-col">
      <CardTitle right={<MoreHorizontal size={16} className="text-slate-600" />}>
        Statystyki skuteczności
      </CardTitle>

      <div className="px-4 pb-2">
        <EffectivenessDonut profit={avg} />
        <div className="mt-2 flex justify-center gap-5 text-xs">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Zysk
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="h-2 w-2 rounded-full bg-slate-700" /> Strata
          </span>
        </div>
      </div>

      <table className="w-full px-2 pb-4 text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wider text-slate-500">
            <th className="px-4 py-2 font-medium">Sygnał</th>
            <th className="px-4 py-2 text-right font-medium">Skuteczność %</th>
            <th className="px-4 py-2 text-right font-medium">Zysk / Ryzyko</th>
          </tr>
        </thead>
        <tbody>
          {mockEffectiveness.map((r, i) => (
            <tr key={i} className="border-t border-slate-800/60">
              <td className="px-4 py-2 text-slate-200">{r.signal}</td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-300">
                {r.successPct}%
              </td>
              <td
                className={
                  'px-4 py-2 text-right tabular-nums ' +
                  (r.rewardRisk >= 1 ? 'text-emerald-400' : 'text-rose-400')
                }
              >
                {r.rewardRisk.toFixed(1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export function ScannerPage() {
  return (
    <div className="p-4 sm:p-6">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
        <EngineList />
        <SignalTuner />
        <EffectivenessStats />
      </div>
    </div>
  )
}
