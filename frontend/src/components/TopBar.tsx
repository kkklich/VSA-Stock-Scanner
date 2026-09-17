// Slim top bar: hamburger (mobile) + page title on the left; the market
// switcher, that market's status and last EOD sync, and a user avatar on the
// right (DOCUMENTATION.md §3). With "All markets" selected the status shows
// the GPW, the home market.

import { Menu } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from './LanguageSwitcher'
import { MarketSwitcher } from './MarketSwitcher'
import { ThemeToggle } from './ThemeToggle'
import { ALL_MARKETS, GPW_MARKET } from '../lib/markets'
import { useMarketScope } from '../hooks/useMarkets'
import { isMarketOpen, lastSyncLabel } from '../lib/marketClock'

// ── Component ─────────────────────────────────────────────────────────────────

export function TopBar({
  title,
  onMenuClick,
}: {
  title: string
  onMenuClick: () => void
}) {
  const { t } = useTranslation()
  // A market the deployment does not serve (a stale stored choice) or "all"
  // shows the GPW's status.
  const { market } = useMarketScope({ allowAll: true })
  const statusMarket = !market || market === ALL_MARKETS ? GPW_MARKET : market
  const open = isMarketOpen(statusMarket)
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/80 px-4 backdrop-blur sm:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <button
          onClick={onMenuClick}
          className="-ml-1 rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 lg:hidden"
          aria-label={t('nav.openMenu')}
        >
          <Menu size={20} />
        </button>
        <h1 className="truncate text-sm font-semibold text-slate-200">
          {title}
        </h1>
      </div>

      <div className="flex items-center gap-3 text-xs sm:gap-5">
        {/* Wide screens only: the market switcher needs the room below xl. */}
        <span className="hidden whitespace-nowrap text-slate-500 xl:inline">
          {t('topbar.lastSync')}{' '}
          <span className="text-slate-300">{lastSyncLabel(statusMarket)}</span>
        </span>
        <span className="flex items-center gap-1.5 text-slate-400">
          <span
            className={
              'h-2 w-2 rounded-full ' +
              (open
                ? 'bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400/70'
                : 'bg-slate-500')
            }
          />
          <span className="hidden sm:inline">{t('topbar.market')}</span>
          <span className={'font-semibold ' + (open ? 'text-emerald-400' : 'text-slate-400')}>
            {open ? t('topbar.open') : t('topbar.closed')}
          </span>
        </span>

        <MarketSwitcher />
        <ThemeToggle />
        <LanguageSwitcher />
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-800 text-[11px] font-semibold text-slate-300 ring-1 ring-slate-700">
          AM
        </div>
      </div>
    </header>
  )
}
