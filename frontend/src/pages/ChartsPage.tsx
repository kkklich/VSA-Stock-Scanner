// Stock detail / charts page — the "detail" half of the master–detail dashboard.
// Reproduces the mockup: signal checklist (Siła / Słabość rynku) on the left,
// detection-settings strip + candlestick chart in the center, and the
// fundamentals / VSA rating / mini-watchlist cards on the right.

import { useState } from 'react'
import { ChevronUp, MoreHorizontal } from 'lucide-react'
import { StockChart } from '../components/StockChart'
import { Card, CardTitle } from '../components/ui'
import { mockDetail, mockMiniWatchlist } from '../data/mockData'
import type { SignalFlag } from '../types'
import { deltaTone, fmtPct, fmtPrice, fmtSigned, ratingTone } from '../lib/format'

/* ── Left column: detected-signal checklist ─────────────────────────────── */

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

function SignalChecklist() {
  return (
    <Card className="flex flex-col">
      <CardTitle>Siła rynku</CardTitle>
      <ul className="px-4 pb-3">
        {mockDetail.strength.map((f) => (
          <SignalRow key={f.name} flag={f} />
        ))}
        <li className="pt-1 text-xs text-slate-500 hover:text-slate-300">
          Inne…
        </li>
      </ul>
      <div className="border-t border-slate-800" />
      <CardTitle>Słabość rynku</CardTitle>
      <ul className="px-4 pb-4">
        {mockDetail.weakness.map((f) => (
          <SignalRow key={f.name} flag={f} />
        ))}
        <li className="pt-1 text-xs text-slate-500 hover:text-slate-300">
          Inne…
        </li>
      </ul>
    </Card>
  )
}

/* ── Center top: detection-settings strip ───────────────────────────────── */

function DetectionSettings() {
  const [sensitivity, setSensitivity] = useState(62)
  const [context, setContext] = useState(10)
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-slate-300">
          Adjust context for signal-detection sensitivity
        </p>
        <ChevronUp size={16} className="text-slate-500" />
      </div>

      <label className="mb-1 block text-xs text-slate-500">Sensitivity</label>
      <input
        type="range"
        min={0}
        max={100}
        value={sensitivity}
        onChange={(e) => setSensitivity(+e.target.value)}
        className="mb-4 w-full accent-emerald-500"
      />

      <label className="mb-1 block text-xs text-slate-500">
        Context window (sessions)
      </label>
      <div className="flex items-center gap-3">
        <input
          type="number"
          value={context}
          onChange={(e) => setContext(+e.target.value)}
          className="w-20 rounded-md border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 focus:border-emerald-500/50 focus:outline-none"
        />
        <button className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500">
          Preview
        </button>
      </div>
    </Card>
  )
}

/* ── Right column cards ─────────────────────────────────────────────────── */

function FundamentalsCard() {
  const f = mockDetail.fundamentals
  const rows = [
    ['Sector', f.sector],
    ['Industry', f.industry],
    ['Market cap', f.marketCap],
  ]
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

function RatingCard() {
  const tone = ratingTone(mockDetail.currentRating)
  return (
    <Card>
      <CardTitle right={<MoreHorizontal size={16} className="text-slate-600" />}>
        Ocena VSA
      </CardTitle>
      <div className="px-4 pb-4">
        <div className="flex items-end gap-2">
          <span className={'text-5xl font-bold tabular-nums ' + tone.text}>
            {mockDetail.currentRating}
          </span>
          <span className="mb-1 text-xs text-slate-500">/ 100</span>
        </div>
        <div className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-500">Zmiana ratingu</span>
            <span className={deltaTone(mockDetail.ratingChange)}>
              {fmtSigned(mockDetail.ratingChange)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Od wczoraj / tygodnia</span>
            <span className="text-emerald-400">+2 / +6</span>
          </div>
        </div>
      </div>
    </Card>
  )
}

function MiniWatchlistCard() {
  return (
    <Card>
      <CardTitle>Watchlista dodatkowo</CardTitle>
      <table className="w-full px-2 pb-3 text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-500">
            <th className="px-4 pb-1 font-medium">Symbol</th>
            <th className="px-4 pb-1 text-right font-medium">Rating</th>
          </tr>
        </thead>
        <tbody>
          {mockMiniWatchlist.map((m) => (
            <tr key={m.ticker} className="hover:bg-slate-800/30">
              <td className="px-4 py-1.5 font-medium text-slate-200">
                {m.ticker}
              </td>
              <td className="px-4 py-1.5 text-right">
                <span className="font-medium text-slate-200">{m.rating}</span>
                <span
                  className={'ml-2 text-xs ' + deltaTone(m.ratingChange)}
                >
                  {fmtSigned(m.ratingChange)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export function ChartsPage() {
  const d = mockDetail
  const tone = ratingTone(d.currentRating)
  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      {/* Asset header */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 className="text-xl font-bold text-slate-100">
          {d.name}{' '}
          <span className="text-slate-500">({d.ticker})</span>
        </h2>
        <span className="text-xl font-semibold text-slate-200">
          ${fmtPrice(d.lastPrice)}
        </span>
        <span className={'text-sm font-medium ' + deltaTone(d.priceChangePct)}>
          {fmtPct(d.priceChangePct)}
        </span>
        <span
          className={
            'ml-auto rounded-md px-2.5 py-1 text-sm font-semibold ring-1 ring-inset ' +
            tone.badge
          }
        >
          VSA {d.currentRating}
        </span>
      </div>

      {/* Three-column detail grid */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[260px_minmax(0,1fr)_300px]">
        {/* Left: signal checklist */}
        <SignalChecklist />

        {/* Center: detection settings + chart */}
        <div className="flex min-w-0 flex-col gap-4">
          <DetectionSettings />
          <Card className="p-3">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-sm font-medium text-slate-300">
                {d.ticker} · 1D
              </span>
              <span className="text-xs text-slate-500">
                TradingView Lightweight Charts
              </span>
            </div>
            <div className="h-[300px] w-full sm:h-[420px]">
              <StockChart candles={d.candles} signals={d.signals} />
            </div>
          </Card>
        </div>

        {/* Right: fundamentals / rating / mini watchlist */}
        <div className="flex flex-col gap-4">
          <FundamentalsCard />
          <RatingCard />
          <MiniWatchlistCard />
        </div>
      </div>
    </div>
  )
}
