// Stub for destinations not yet designed (Dashboard, Filters, Stats, Settings).
// Keeps navigation complete while the three primary screens are built out.

import { Construction } from 'lucide-react'

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="grid h-full place-items-center p-6">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="grid h-14 w-14 place-items-center rounded-2xl border border-slate-800 bg-slate-900 text-slate-500">
          <Construction size={24} />
        </div>
        <h2 className="text-lg font-semibold text-slate-200">{title}</h2>
        <p className="max-w-sm text-sm text-slate-500">
          This screen is part of the StockPilot blueprint and will be built out
          next. The Watchlist, Charts, and Scanner views are ready to explore.
        </p>
      </div>
    </div>
  )
}
