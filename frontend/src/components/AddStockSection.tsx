import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ApiError, apiFetch } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { useMarkets } from '../hooks/useMarkets'

const FIELD = 'mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100'

export function AddStockSection() {
  const { user } = useAuth()
  // Reset pending form state when the signed-in account changes.
  return <StockForm key={user?.id ?? 'guest'} />
}

function StockForm() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const markets = useMarkets({ enabled: !!user })
  const [ticker, setTicker] = useState('')
  const [name, setName] = useState('')
  const [country, setCountry] = useState('')
  const [market, setMarket] = useState('gpw')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState<{ ticker: string; name: string } | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!user || busy) return
    setBusy(true)
    setError('')
    setSaved(null)
    try {
      const stock = await apiFetch<{ ticker: string; name: string }>('/api/custom-stocks', {
        method: 'POST',
        headers: { 'X-Expected-User-Id': String(user.id) },
        body: JSON.stringify({ ticker: ticker.trim(), name: name.trim(), country: country.trim(), market }),
      })
      setSaved(stock)
      setTicker('')
      setName('')
    } catch (err) {
      const code = err instanceof ApiError ? err.code : undefined
      setError(t(`addStock.errors.${code}`, { defaultValue: t('addStock.errors.failed') }))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 sm:p-5">
      <h2 className="text-sm font-semibold text-slate-200">{t('addStock.title')}</h2>
      <p className="mt-1 text-xs leading-relaxed text-slate-500">{t('addStock.hint')}</p>
      {!user ? (
        <Link to="/login" className="mt-4 inline-block text-sm text-emerald-400">{t('addStock.signIn')}</Link>
      ) : (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-4">
          <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2 disabled:opacity-60">
            <label className="text-xs text-slate-300">{t('addStock.ticker')}
              <input className={FIELD} required maxLength={20} value={ticker} onChange={e => setTicker(e.target.value)} placeholder="KGH / AAPL" />
            </label>
            <label className="text-xs text-slate-300">{t('addStock.name')}
              <input className={FIELD} required maxLength={200} value={name} onChange={e => setName(e.target.value)} />
            </label>
            <label className="text-xs text-slate-300">{t('addStock.country')}
              <input className={FIELD} required maxLength={100} value={country} onChange={e => setCountry(e.target.value)} />
            </label>
            <label className="text-xs text-slate-300">{t('addStock.market')}
              <select className={FIELD} required value={market} onChange={e => setMarket(e.target.value)}>
                {(markets ?? []).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </label>
          </fieldset>
          <button type="submit" disabled={busy || !markets?.length} className="self-start rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {t(busy ? 'addStock.saving' : 'addStock.submit')}
          </button>
          {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
          {saved && <p role="status" className="text-sm text-emerald-400">
            {t('addStock.success')}{' '}<Link className="underline" to={`/stock/${encodeURIComponent(saved.ticker)}`}>{saved.name} ({saved.ticker.toUpperCase()})</Link>
          </p>}
        </form>
      )}
    </section>
  )
}
