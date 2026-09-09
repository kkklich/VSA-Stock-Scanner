// The ranking table's 52-week distance cell. Lives in its own file so the
// column registry (lib/rankingColumns.tsx) stays component-free — a module
// mixing components with plain exports cannot be hot-swapped by Vite's Fast
// Refresh (react-refresh's only-export-components rule).

import { fmtPct } from '../lib/format'

/**
 * One 52-week distance cell: the percentage plus a "NEW" chip when the latest
 * session actually set the extreme (a breakout/breakdown, not just proximity).
 */
export function Range52wCell({
  pct,
  isNew,
  newTone,
  newLabel,
}: {
  pct: number | null
  isNew: boolean
  newTone: string
  newLabel: string
}) {
  if (pct === null) return <span className="text-slate-600">—</span>
  return (
    <span className="inline-flex items-center justify-end gap-1.5">
      {isNew && (
        <span
          className={
            'rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide ring-1 ' +
            newTone
          }
        >
          {newLabel}
        </span>
      )}
      <span className="tabular-nums text-slate-300">{fmtPct(pct)}</span>
    </span>
  )
}
