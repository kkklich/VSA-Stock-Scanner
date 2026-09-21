// The amber note above a pooled ("All markets") list when its rows are not all
// from the same session. The reasoning and the logic live in `lib/sessions.ts`.

import { useTranslation } from 'react-i18next'
import { Clock } from 'lucide-react'
import { sessionMismatch, type SessionRow } from '../lib/sessions'

export function SessionNote({
  rows,
  enabled = true,
  className = '',
}: {
  rows: readonly SessionRow[]
  /** Only meaningful when markets are pooled; one market has one calendar. */
  enabled?: boolean
  className?: string
}) {
  const { t } = useTranslation()
  const mismatch = enabled ? sessionMismatch(rows) : null
  if (!mismatch) return null
  return (
    <p
      className={
        'flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300 ' +
        className
      }
    >
      <Clock size={14} className="mt-0.5 shrink-0" />
      <span>{t('markets.sessionMismatch', mismatch)}</span>
    </p>
  )
}
