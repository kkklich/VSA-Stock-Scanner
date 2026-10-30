import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth'
import { useWatchlists } from '../hooks/useWatchlists'
import { loadFavorites } from '../lib/favorites'

export function WatchlistControls({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const { user, loading, config } = useAuth()
  const state = useWatchlists()
  const [mode, setMode] = useState<'create' | 'rename' | 'delete' | null>(null)
  const [name, setName] = useState('')
  useEffect(() => { setMode(null) }, [user?.id, state.activeId])
  const active = state.lists.find((list) => list.id === state.activeId)
  const button = 'rounded-md border border-slate-700 px-3 py-1.5 text-sm disabled:opacity-40'
  if (loading) return <p role="status">{t('watchlists.loading')}</p>
  if (!user) return compact ? null : <p className="text-sm text-slate-400">
    {t('watchlists.local')} {config?.enabled !== false && <Link to="/login" className="text-emerald-400">{t('watchlists.signIn')}</Link>}
  </p>
  return <section className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 p-3 text-slate-300" aria-label={t('watchlists.title')}>
    <label className="flex items-center gap-2 text-sm">
      {t('watchlists.active')}
      <select aria-label={t('watchlists.active')} className="max-w-60 rounded-md border border-slate-700 bg-slate-900 p-1.5" value={state.activeId} disabled={state.busy} onChange={(event) => { state.select(event.target.value); setMode(null) }}>
        {state.lists.map((list) => <option key={list.id} value={list.id}>{list.name} ({list.tickers.length})</option>)}
      </select>
    </label>
    {!compact && <>
      <button className={button} disabled={state.busy || state.lists.length >= 20} onClick={() => { setMode('create'); setName('') }}>{t('watchlists.create')}</button>
      <button className={button} disabled={state.busy} onClick={() => { setMode('rename'); setName(active?.name ?? '') }}>{t('watchlists.rename')}</button>
      <button className={button} disabled={state.busy || state.lists.length < 2} onClick={() => setMode('delete')}>{t('watchlists.delete')}</button>
      {Object.values(loadFavorites()).some(Boolean) && <button className={button} disabled={state.busy} onClick={() => { void state.importLocal() }}>{t('watchlists.import')}</button>}
      <p className="w-full text-xs text-slate-500">{t('watchlists.hint')}</p>
    </>}
    {state.busy && !state.error && <span role="status" className="text-sm">{t('watchlists.loading')}</span>}
    {state.error && <div role="alert" className="w-full text-sm text-rose-400">
      {t(`watchlists.errors.${state.error}`, { defaultValue: t('watchlists.errors.failed') })}{' '}
      <button className={button} onClick={state.reload}>{t('watchlists.retry')}</button>
    </div>}
    {!compact && mode && <form className="flex w-full flex-wrap items-center gap-2" onSubmit={async (event) => {
      event.preventDefault()
      const success = mode === 'delete' ? await state.remove() : mode === 'create' ? await state.create(name.trim()) : await state.rename(name.trim())
      if (success) setMode(null)
    }}>
      {mode === 'delete' ? <span>{t('watchlists.confirmDelete', { name: active?.name })}</span> : <input autoFocus aria-label={t('watchlists.name')} className="rounded-md border border-slate-700 bg-slate-900 p-2" value={name} required maxLength={80} onChange={(event) => setName(event.target.value)} />}
      <button type="submit" className={button} disabled={state.busy || (mode !== 'delete' && !name.trim())}>{t(mode === 'delete' ? 'watchlists.delete' : 'watchlists.save')}</button>
      <button type="button" className={button} onClick={() => setMode(null)}>{t('watchlists.cancel')}</button>
    </form>}
  </section>
}
