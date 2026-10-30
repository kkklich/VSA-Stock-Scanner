import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { portfolioRequest, type Instrument, type Portfolio, type Portfolios, type Transaction } from '../api/portfoliosApi'
import { useAuth } from '../hooks/useAuth'
import { currencyLabel, fmtMoney, fmtPct } from '../lib/format'

const input = 'w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm'
const button = 'rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40'
type Save = (method: string, path: string, payload?: unknown) => Promise<boolean>
const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date())

function PortfolioForm({ portfolio, save, busy, close }: { portfolio?: Portfolio; save: Save; busy: boolean; close?: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState(portfolio?.name ?? '')
  const [broker, setBroker] = useState(portfolio?.broker ?? '')
  const [costMethod, setCostMethod] = useState(portfolio?.costMethod ?? 'fifo')
  const [editVersion] = useState(portfolio?.version)
  const changedElsewhere = !!portfolio && portfolio.version !== editVersion
  const id = useRef<string | null>(null)
  async function submit(event: FormEvent) {
    event.preventDefault()
    id.current ??= crypto.randomUUID()
    if (await save(portfolio ? 'PATCH' : 'POST', portfolio ? `/${portfolio.id}` : '', {
      ...(portfolio ? { version: editVersion } : { id: id.current }), name: name.trim(), broker: broker.trim(), costMethod,
    })) { setName(''); setBroker(''); id.current = null; close?.() }
  }
  return <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
    <label className="min-w-40 flex-1 text-sm">{t('portfolio.name')}<input className={input} required maxLength={80} value={name} disabled={busy} onChange={e => { setName(e.target.value); id.current = null }} /></label>
    <label className="min-w-40 flex-1 text-sm">{t('portfolio.broker')}<input className={input} required maxLength={80} value={broker} disabled={busy} onChange={e => { setBroker(e.target.value); id.current = null }} /></label>
    <label className="min-w-40 flex-1 text-sm">{t('portfolio.costMethod')}<select className={input} disabled={busy} value={costMethod} onChange={e => { setCostMethod(e.target.value as Portfolio['costMethod']); id.current = null }}><option value="fifo">{t('portfolio.fifo')}</option><option value="moving_average">{t('portfolio.moving_average')}</option></select></label>
    <button className={button + ' text-emerald-400'} disabled={busy || changedElsewhere || !name.trim() || !broker.trim()}>{t(portfolio ? 'portfolio.save' : 'portfolio.create')}</button>
    {close && <button type="button" className={button} disabled={busy} onClick={close}>{t('portfolio.cancel')}</button>}
    {changedElsewhere && <p role="alert" className="w-full text-sm text-amber-400">{t('portfolio.editChanged')}</p>}
  </form>
}

function TradeForm({ portfolio, instruments, busy, save }: { portfolio: Portfolio; instruments: Instrument[]; busy: boolean; save: Save }) {
  const { t } = useTranslation()
  const [trade, setTrade] = useState({ ticker: '', date: today(), side: 'buy', quantity: '', price: '', fees: '0' })
  const id = useRef<string | null>(null)
  const instrument = instruments.find(i => i.ticker.toLowerCase() === trade.ticker.trim().toLowerCase())
  function edit(key: keyof typeof trade, value: string) { id.current = null; setTrade(prev => ({ ...prev, [key]: value })) }
  return <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={async event => {
    event.preventDefault()
    if (!instrument) return
    id.current ??= crypto.randomUUID()
    if (await save('POST', `/${portfolio.id}/transactions`, {
      ...trade, ticker: instrument.ticker, currency: instrument.currency, id: id.current, version: portfolio.version,
    })) { id.current = null; setTrade(prev => ({ ...prev, quantity: '', price: '', fees: '0' })) }
  }}>
    <label className="text-sm">{t('portfolio.side')}<select className={input} value={trade.side} disabled={busy} onChange={e => edit('side', e.target.value)}><option value="buy">{t('portfolio.buy')}</option><option value="sell">{t('portfolio.sell')}</option></select></label>
    <label className="text-sm">{t('portfolio.date')}<input className={input} type="date" required max={today()} value={trade.date} disabled={busy} onChange={e => edit('date', e.target.value)} /></label>
    <label className="text-sm">{t('portfolio.instrument')}<input className={input} list="portfolio-instruments" placeholder="KGH, AAPL.US…" required maxLength={20} value={trade.ticker} disabled={busy} onChange={e => edit('ticker', e.target.value)} /></label>
    <datalist id="portfolio-instruments">{instruments.map(i => <option key={i.ticker} value={i.ticker}>{i.name} · {i.market.toUpperCase()}</option>)}</datalist>
    <label className="text-sm">{t('portfolio.currency')}<input className={input} readOnly value={instrument ? currencyLabel(instrument.currency) : '—'} /></label>
    {(['quantity', 'price', 'fees'] as const).map(key => <label key={key} className="text-sm">{t(`portfolio.${key}`)}<input className={input} type="number" required min={key === 'fees' ? '0' : '0.00000001'} max="1000000000000" step="0.00000001" value={trade[key]} disabled={busy} onChange={e => edit(key, e.target.value)} /></label>)}
    <button className={button + ' self-end text-emerald-400'} disabled={busy || !instrument}>{t('portfolio.addTransaction')}</button>
    <p className="text-xs text-slate-400 sm:col-span-2 lg:col-span-4">{instrument ? `${instrument.name} · ${instrument.market.toUpperCase()} · ` : ''}{t('portfolio.tradeHint')}</p>
  </form>
}

function PortfolioDetail({ portfolio, instruments, save, busy }: { portfolio: Portfolio; instruments: Instrument[]; save: Save; busy: boolean }) {
  const { t, i18n } = useTranslation()
  const [editing, setEditing] = useState(false)
  const money = (n: number | null, currency: string) => n === null ? '—' : fmtMoney(n, currency)
  const quantity = (n: number | string) => Number(n).toLocaleString(i18n.language, { maximumFractionDigits: 8 })
  const pnl = (amount: number | null, pct: number | null, currency: string) => `${money(amount, currency)}${pct === null ? '' : ` (${fmtPct(pct)})`}`
  const trades = portfolio.transactions.map((trade, index) => ({ trade, index })).sort((a, b) => b.trade.date.localeCompare(a.trade.date) || b.index - a.index).map(({ trade }) => trade)
  async function remove(trade: Transaction) {
    if (window.confirm(t('portfolio.confirmTransaction'))) await save('DELETE', `/${portfolio.id}/transactions/${trade.id}?version=${portfolio.version}`)
  }
  return <div className="space-y-5">
    <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      {editing ? <PortfolioForm portfolio={portfolio} save={save} busy={busy} close={() => setEditing(false)} /> : <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto"><h2 className="text-lg font-semibold">{portfolio.name}</h2><p className="text-sm text-slate-400">{portfolio.broker} · {t(`portfolio.${portfolio.costMethod}`)}</p></div>
        <button className={button} disabled={busy} onClick={() => setEditing(true)}>{t('portfolio.edit')}</button>
        <button className={button + ' text-rose-400'} disabled={busy} onClick={async () => { if (window.confirm(t('portfolio.confirmPortfolio', { name: portfolio.name }))) await save('DELETE', `/${portfolio.id}?version=${portfolio.version}`) }}>{t('portfolio.delete')}</button>
      </div>}
    </section>
    <div className="grid gap-3 lg:grid-cols-2">{portfolio.totals.map(total => <section key={total.currency} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <h3 className="mb-3 font-semibold">{currencyLabel(total.currency)}</h3>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-slate-400">{t('portfolio.marketValue')}</dt><dd className="text-xl font-semibold">{money(total.marketValue, total.currency)}</dd></div>
        <div><dt className="text-slate-400">{t('portfolio.cost')}</dt><dd>{money(total.cost, total.currency)}</dd></div>
        <div><dt className="text-slate-400">{t('portfolio.unrealized')}</dt><dd className={(total.unrealizedPnl ?? 0) < 0 ? 'text-rose-400' : 'text-emerald-400'}>{pnl(total.unrealizedPnl, total.unrealizedPnlPct, total.currency)}</dd></div>
        <div><dt className="text-slate-400">{t('portfolio.realized')}</dt><dd>{money(total.realizedPnl, total.currency)}</dd></div>
      </dl>
      {!!total.missingQuotes && <p className="mt-3 text-sm text-amber-400">{t('portfolio.missingQuotes', { count: total.missingQuotes })}</p>}
    </section>)}</div>
    <section className="rounded-xl border border-slate-800 p-4"><h3 className="mb-3 font-semibold">{t('portfolio.addTransaction')}</h3><TradeForm portfolio={portfolio} instruments={instruments} busy={busy} save={save} /></section>
    <section><h3 className="mb-3 font-semibold">{t('portfolio.holdings')}</h3>
      {!portfolio.positions.length ? <p className="text-sm text-slate-400">{t('portfolio.emptyHoldings')}</p> : <div className="overflow-x-auto"><table className="w-full whitespace-nowrap text-left text-sm"><thead className="text-xs text-slate-400"><tr>{['instrument', 'quantity', 'averagePrice', 'currentPrice', 'marketValue', 'unrealized', 'realized', 'quoteDate'].map(key => <th key={key} className="p-3">{t(`portfolio.${key}`)}</th>)}</tr></thead><tbody>{portfolio.positions.map(p => <tr key={`${p.ticker}:${p.currency}`} className="border-t border-slate-800">
        <td className="p-3"><Link className="text-emerald-400 hover:underline" to={`/stock/${encodeURIComponent(p.ticker)}`}>{p.ticker.toUpperCase()}</Link></td><td className="p-3">{quantity(p.quantity)}</td><td className="p-3">{money(p.averagePrice, p.currency)}</td><td className="p-3">{money(p.currentPrice, p.currency)}</td><td className="p-3">{money(p.marketValue, p.currency)}</td><td className="p-3">{pnl(p.unrealizedPnl, p.unrealizedPnlPct, p.currency)}</td><td className="p-3">{money(p.realizedPnl, p.currency)}</td><td className="p-3">{p.quoteDate ?? t('portfolio.noQuote')}{p.quoteAsOf && <span className="block text-xs text-slate-400">{new Date(p.quoteAsOf).toLocaleTimeString(i18n.language)}</span>}{p.quoteSource && <span className="block text-xs text-slate-400">{t(`portfolio.quote_${p.quoteSource}`)}</span>}{p.quantity > 0 && p.quoteAgeDays !== null && p.quoteAgeDays > 7 && <span className="block text-xs text-amber-400">{t('portfolio.oldQuote', { count: p.quoteAgeDays })}</span>}</td>
      </tr>)}</tbody></table></div>}
    </section>
    <section><h3 className="mb-3 font-semibold">{t('portfolio.transactions')}</h3><div className="overflow-x-auto"><table className="w-full whitespace-nowrap text-left text-sm"><thead className="text-xs text-slate-400"><tr>{['date', 'side', 'instrument', 'quantity', 'price', 'fees', 'actions'].map(key => <th key={key} className="p-3">{t(`portfolio.${key}`)}</th>)}</tr></thead><tbody>{trades.map(trade => <tr key={trade.id} className="border-t border-slate-800"><td className="p-3">{trade.date}</td><td className="p-3">{t(`portfolio.${trade.side}`)}</td><td className="p-3">{trade.ticker.toUpperCase()}</td><td className="p-3">{quantity(trade.quantity)}</td><td className="p-3">{money(Number(trade.price), trade.currency)}</td><td className="p-3">{money(Number(trade.fees), trade.currency)}</td><td className="p-3"><button className={button} disabled={busy} onClick={() => remove(trade)}>{t('portfolio.delete')}</button></td></tr>)}</tbody></table></div></section>
  </div>
}

function AccountPortfolios() {
  const { t, i18n } = useTranslation()
  const [data, setData] = useState<Portfolios | null>(null)
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [stale, setStale] = useState(false)
  const [creating, setCreating] = useState(false)
  const [saved, setSaved] = useState(false)
  const alive = useRef(true)
  const mutation = useRef(false)
  const request = useRef<AbortController | null>(null)
  const write = useRef<AbortController | null>(null)
  const code = (e: unknown) => e instanceof ApiError && e.code ? e.code : 'failed'
  const reload = useCallback(async () => {
    request.current?.abort()
    const abort = new AbortController()
    request.current = abort
    setLoading(true)
    try {
      const [next, options] = await Promise.all([
        portfolioRequest<Portfolios>('GET', '', undefined, abort.signal),
        portfolioRequest<Instrument[]>('GET', '/instruments', undefined, abort.signal),
      ])
      if (abort.signal.aborted || !alive.current) return
      setData(next); setInstruments(options); setStale(false)
      setSelected(current => next.items.some(p => p.id === current) ? current : next.items[0]?.id ?? '')
    } catch (failure) {
      if (!abort.signal.aborted && alive.current) { setStale(true); setError(code(failure)) }
    } finally { if (!abort.signal.aborted && alive.current) setLoading(false) }
  }, [])
  useEffect(() => {
    alive.current = true
    void reload()
    const refresh = () => { if (document.visibilityState === 'visible' && !mutation.current) void reload() }
    const timer = window.setInterval(refresh, 60000)
    window.addEventListener('focus', refresh)
    return () => { alive.current = false; request.current?.abort(); write.current?.abort(); window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [reload])
  const save: Save = async (method, path, payload) => {
    if (mutation.current || stale || loading) return false
    mutation.current = true; setBusy(true); setError(null); setSaved(false)
    const abort = new AbortController()
    write.current = abort
    try {
      await portfolioRequest(method, path, payload, abort.signal)
      if (!alive.current || abort.signal.aborted) return false
      if (method === 'POST' && path === '') setSelected((payload as { id: string }).id)
      setSaved(true)
      await reload()
      return true
    } catch (failure) {
      if (alive.current && !abort.signal.aborted) {
        setError(code(failure))
        // Reload versions after a conflict; never silently replay a sale against newer holdings.
        if (failure instanceof ApiError && failure.code === 'conflict') await reload()
      }
      return false
    } finally { mutation.current = false; if (alive.current) setBusy(false) }
  }
  const active = data?.items.find(p => p.id === selected)
  const disabled = busy || stale || loading
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center gap-3"><h1 className="mr-auto text-xl font-semibold">{t('portfolio.title')}</h1><button className={button} disabled={busy || loading} onClick={() => { setError(null); void reload() }}>{t('portfolio.refresh')}</button><button className={button} disabled={disabled} onClick={() => setCreating(v => !v)}>{t('portfolio.create')}</button></div>
    <p className="text-sm text-slate-400">{t('portfolio.valuationHint')}</p>
    <details className="rounded-lg border border-slate-800 p-3 text-sm text-slate-400"><summary className="cursor-pointer text-slate-200">{t('portfolio.assumptions')}</summary><ul className="mt-3 list-disc space-y-2 pl-5">{['costHint', 'priceHint', 'returnHint', 'scopeHint'].map(key => <li key={key}>{t(`portfolio.${key}`)}</li>)}</ul><p className="mt-3">{t('portfolio.sources')}: <a className="text-emerald-400 hover:underline" href="https://www.ibkrguides.com/ibkrdesktop/account-portfolio.htm" target="_blank" rel="noreferrer">Interactive Brokers</a> · <a className="text-emerald-400 hover:underline" href="https://help.portfolio-performance.info/en/concepts/cost-methodology/" target="_blank" rel="noreferrer">Portfolio Performance</a></p></details>
    {error && <p role="alert" className="rounded-md border border-rose-500/30 p-3 text-sm text-rose-400">{t(`portfolio.errors.${error}`, { defaultValue: t('portfolio.errors.failed') })}</p>}
    {saved && <p role="status" className="text-sm text-emerald-400">{t('portfolio.saved')}</p>}
    {loading && <p role="status" className="text-sm text-slate-400">{t('portfolio.loading')}</p>}
    {data && <>
      {(creating || !data.items.length) && <section className="rounded-xl border border-slate-800 p-4"><PortfolioForm save={async (...args) => { const ok = await save(...args); if (ok) setCreating(false); return ok }} busy={disabled} /></section>}
      {!!data.items.length && <label className="block max-w-md text-sm">{t('portfolio.choose')}<select className={input} value={selected} disabled={busy} onChange={e => { setSelected(e.target.value); setError(null); setSaved(false) }}>{data.items.map(p => <option key={p.id} value={p.id}>{p.name} · {p.broker}</option>)}</select></label>}
      {active && <PortfolioDetail key={active.id} portfolio={active} instruments={instruments} save={save} busy={disabled} />}
      <p className="text-xs text-slate-500">{t('portfolio.valuedAt')}: {new Date(data.valuedAt).toLocaleString(i18n.language)}</p>
    </>}
  </div>
}

export function PortfolioPage() {
  const { user, loading } = useAuth()
  const { t } = useTranslation()
  return <div className="p-4 sm:p-6">{loading ? <p role="status">{t('portfolio.loading')}</p> : user ? <AccountPortfolios key={user.id} /> : <section className="rounded-xl border border-slate-800 p-5"><h1 className="mb-2 text-xl font-semibold">{t('portfolio.title')}</h1><p className="mb-4 text-sm text-slate-400">{t('portfolio.signInHint')}</p><Link className={button} to="/login" state={{ from: '/portfolio' }}>{t('portfolio.signIn')}</Link></section>}</div>
}
