import { useTranslation } from 'react-i18next'

interface LongTermFactorBarProps {
  value: number | null
  label: string
}

/** A fixed 0–100 scale; the neutral colour does not encode a trading signal. */
export function LongTermFactorBar({ value, label }: LongTermFactorBarProps) {
  const { t, i18n } = useTranslation()
  const score = value !== null && Number.isFinite(value)
    ? Math.min(100, Math.max(0, value))
    : null

  if (score === null) {
    return <span
      role="img"
      aria-label={`${label}: ${t('longTerm.unscored')}`}
      className="block w-full min-w-0 text-right tabular-nums text-slate-500"
    >—</span>
  }

  const formatted = score.toLocaleString(i18n.resolvedLanguage ?? i18n.language, {
    maximumFractionDigits: 1,
  })

  return <div
    role="meter"
    aria-label={label}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={score}
    aria-valuetext={`${formatted} / 100`}
    className="w-full min-w-0 space-y-1.5"
  >
    <span aria-hidden="true" className="block text-right tabular-nums text-slate-200">
      {formatted}
    </span>
    <span aria-hidden="true" className="block h-1 w-full overflow-hidden rounded-full bg-slate-800">
      <span className="block h-full rounded-full bg-slate-400" style={{ width: `${score}%` }} />
    </span>
  </div>
}
