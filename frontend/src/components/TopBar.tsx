// Slim top bar: hamburger (mobile) + page title on the left; market status,
// last EOD sync, and a user avatar on the right (DOCUMENTATION.md §3).

import { Menu } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from './LanguageSwitcher'
import { ThemeToggle } from './ThemeToggle'

// ── Warsaw-time helpers ───────────────────────────────────────────────────────

function getWarsawInfo() {
  const now = new Date()
  // toLocaleDateString with en-CA gives YYYY-MM-DD
  const dateStr = now.toLocaleDateString('en-CA', { timeZone: 'Europe/Warsaw' })
  const timeStr = now.toLocaleTimeString('en-US', {
    timeZone: 'Europe/Warsaw',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  const [h, min] = timeStr.split(':').map(Number)
  const minutesInDay = h * 60 + min
  const [yr, mo, dy] = dateStr.split('-').map(Number)
  // Build a local noon date so getDay() reliably returns the Warsaw weekday.
  const dow = new Date(yr, mo - 1, dy, 12).getDay() // 0=Sun … 6=Sat
  return { dateStr, minutesInDay, dow, yr, mo, dy }
}

/** Label for the most recent GPW EOD data availability (Mon–Fri, data at 18:00 Warsaw). */
function computeLastSyncLabel(): string {
  const { dateStr, minutesInDay, dow, yr, mo, dy } = getWarsawInfo()
  const isWeekday = dow >= 1 && dow <= 5
  // Today's data is available on a weekday at or after 18:00.
  if (isWeekday && minutesInDay >= 18 * 60) return `${dateStr} 18:00`
  // Otherwise step back to the most recent weekday.
  const d = new Date(yr, mo - 1, dy, 12)
  do {
    d.setDate(d.getDate() - 1)
  } while (d.getDay() === 0 || d.getDay() === 6)
  return (
    `${d.getFullYear()}-` +
    `${String(d.getMonth() + 1).padStart(2, '0')}-` +
    `${String(d.getDate()).padStart(2, '0')} 18:00`
  )
}

/** True while the GPW continuous session is running (Mon–Fri 09:00–17:05 Warsaw). */
function isMarketOpen(): boolean {
  const { minutesInDay, dow } = getWarsawInfo()
  return dow >= 1 && dow <= 5 && minutesInDay >= 9 * 60 && minutesInDay < 17 * 60 + 5
}

// ── Component ─────────────────────────────────────────────────────────────────

export function TopBar({
  title,
  onMenuClick,
}: {
  title: string
  onMenuClick: () => void
}) {
  const open = isMarketOpen()
  const { t } = useTranslation()
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
        <span className="hidden text-slate-500 md:inline">
          {t('topbar.lastSync')}{' '}
          <span className="text-slate-300">{computeLastSyncLabel()}</span>
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

        <ThemeToggle />
        <LanguageSwitcher />
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-800 text-[11px] font-semibold text-slate-300 ring-1 ring-slate-700">
          AM
        </div>
      </div>
    </header>
  )
}
