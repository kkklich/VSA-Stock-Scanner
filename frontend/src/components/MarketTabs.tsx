// An on-page market picker for the screens that show one market at a time
// (heatmap, investment), used when the top bar says "All markets".

import { useTranslation } from 'react-i18next'
import type { ApiMarket } from '../api/stocksApi'
import { MARKET_CODES } from '../lib/markets'
import { InfoTip } from './ui'

export function MarketTabs({
  markets,
  value,
  onChange,
}: {
  markets: ApiMarket[]
  value: string
  onChange: (id: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-1.5">
      <div
        role="group"
        aria-label={t('markets.label')}
        className="flex flex-wrap overflow-hidden rounded-lg border border-slate-700"
      >
        {markets.map((m) => {
          const active = m.id === value
          return (
            <button
              key={m.id}
              type="button"
              aria-pressed={active}
              title={t(`markets.name.${m.id}`, { defaultValue: m.name })}
              onClick={() => onChange(m.id)}
              className={
                'px-2.5 py-1.5 text-xs font-medium transition-colors ' +
                (active
                  ? 'bg-slate-700 text-slate-100'
                  : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200')
              }
            >
              {m.id === 'gpw' ? 'GPW' : (MARKET_CODES[m.id] ?? m.shortName)}
            </button>
          )
        })}
      </div>
      <InfoTip text={t('markets.oneAtATime')} />
    </div>
  )
}
