// The market switcher in the top bar: which stock market the list pages show.
// Only rendered when the deployment serves more than one market, so a
// GPW-only site looks exactly as it always did.

import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMarkets } from '../hooks/useMarkets'
import {
  ALL_MARKETS,
  effectiveMarket,
  GPW_MARKET,
  useMarketSelection,
} from '../lib/markets'

export function MarketSwitcher() {
  const { t } = useTranslation()
  const markets = useMarkets()
  const { selection, setSelection } = useMarketSelection()
  if (!markets || markets.length <= 1) return null

  const value =
    effectiveMarket(selection, markets.map((m) => m.id), { allowAll: true }) ??
    GPW_MARKET

  return (
    <label className="flex items-center gap-1.5" title={t('markets.label')}>
      <Globe size={14} className="hidden text-slate-500 sm:block" aria-hidden />
      <select
        value={value}
        onChange={(e) => setSelection(e.target.value)}
        aria-label={t('markets.label')}
        className="max-w-[6.5rem] rounded-md border sm:max-w-[9.5rem] border-slate-700 bg-slate-900 py-1 pl-2 pr-6 text-[11px] font-semibold text-slate-200 focus:border-emerald-500/50 focus:outline-none"
      >
        {markets.map((m) => (
          <option key={m.id} value={m.id}>
            {t(`markets.short.${m.id}`, { defaultValue: m.shortName })}
          </option>
        ))}
        <option value={ALL_MARKETS}>{t('markets.all')}</option>
      </select>
    </label>
  )
}
