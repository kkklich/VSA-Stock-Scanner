import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { fetchRanking, type ApiStockSignals } from '../api/stocksApi'
import { journalRequest, type JournalEntry, type JournalPage, type JournalStatus, type NewJournalEntry } from '../api/journalApi'
import { useAuth } from '../hooks/useAuth'
import { useStockDetail } from '../hooks/useStockDetail'
import { settingsQueryValue } from '../lib/vsaSettings'
import { fmtMoney, fmtPct } from '../lib/format'
import { StockChart, type MethodOverlay } from './StockChart'
import type { VsaSignal } from '../types'

const button = 'rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40'
const input = 'w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm text-slate-200'
const statuses: JournalStatus[] = ['observing', 'confirmed', 'invalidated', 'closed']
type Props = { ticker?: string; data?: ApiStockSignals; overlays?: MethodOverlay[]; signals?: VsaSignal[]; loading?: boolean }

function errorCode(error: unknown) {
  return error instanceof ApiError && error.code ? error.code : 'failed'
}

function ErrorNotice({ code, retry }: { code: string; retry?: () => void }) {
  const { t } = useTranslation()
  return <div role="alert" className="rounded-md border border-rose-500/30 p-3 text-sm text-rose-400">
    {t(`journal.errors.${code}`, { defaultValue: t('journal.errors.failed') })}
    {retry && <button className={button + ' ml-2'} onClick={retry}>{t('journal.retry')}</button>}
  </div>
}

function Composer({ data, overlays = [], signals = [], loading, saved }: Props & { data: ApiStockSignals; saved: () => void }) {
  const { t } = useTranslation()
  const [note, setNote] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [invalidation, setInvalidation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const request = useRef<AbortController | null>(null)
  const prepared = useRef<NewJournalEntry | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  function edited() { prepared.current = null; setSuccess(false) }

  return <form className="flex flex-col gap-3" onSubmit={async (event) => {
    event.preventDefault()
    if (request.current || loading || !data.history.length || !note.trim()) return
    const abort = new AbortController()
    request.current = abort
    setBusy(true); setError(null); setSuccess(false)
    try {
      if (!prepared.current) {
        // Capture before awaiting the ranking: an automatic quote refresh must not change evidence.
        const captured = structuredClone(data)
        const history = captured.history.slice(-5000)
        const first = history[0].time
        const last = history[history.length - 1]
        const layers = structuredClone(overlays)
        if (signals.length) layers.push({
          methodId: 'vsa', color: '#10b981', directionalColor: true,
          signals: signals.map((signal) => ({ date: signal.date, label: signal.signalName, type: signal.type })),
        })
        const ranking = await fetchRanking({ tickers: [captured.ticker], market: captured.market ?? 'gpw', pageSize: 1, settings: settingsQueryValue() })
        if (abort.signal.aborted) return
        const row = ranking.items.find((item) => item.ticker.toUpperCase() === captured.ticker.toUpperCase())
        prepared.current = {
          id: crypto.randomUUID(), ticker: captured.ticker, note: note.trim(), confirmation: confirmation.trim(), invalidation: invalidation.trim(),
          snapshot: {
            schemaVersion: 1, name: captured.name ?? captured.ticker, currency: captured.currency ?? 'PLN', market: captured.market ?? 'gpw',
            interval: captured.interval ?? '1d', referencePrice: last.close,
            rating: row?.methodResults?.vsa?.available ? captured.currentRating : null,
            combinedScore: row?.combinedScore ?? null, ratingSession: row?.lastSession ?? null,
            methodScores: Object.values(row?.methodResults ?? {}).map((method) => ({ methodId: method.methodId, score: method.available ? method.score : null, detail: method.detail })),
            history, overlays: layers.map((layer) => ({ ...layer, signals: layer.signals.filter((signal) => signal.date >= first && signal.date <= last.time) })),
          },
        }
      }
      await journalRequest<JournalEntry>('POST', '', prepared.current, abort.signal)
      if (abort.signal.aborted) return
      prepared.current = null
      setNote(''); setConfirmation(''); setInvalidation(''); setSuccess(true); saved()
    } catch (failure) { if (!abort.signal.aborted) setError(errorCode(failure)) }
    finally { if (!abort.signal.aborted) { setBusy(false); request.current = null } }
  }}>
    <p className="text-sm text-slate-400">{t('journal.captureHint')}</p>
    <label className="text-sm">{t('journal.note')}<textarea className={input} value={note} disabled={busy} required maxLength={5000} rows={3} onChange={(event) => { edited(); setNote(event.target.value) }} /></label>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm">{t('journal.confirmation')}<textarea className={input} value={confirmation} disabled={busy} maxLength={5000} rows={2} onChange={(event) => { edited(); setConfirmation(event.target.value) }} /></label>
      <label className="text-sm">{t('journal.invalidation')}<textarea className={input} value={invalidation} disabled={busy} maxLength={5000} rows={2} onChange={(event) => { edited(); setInvalidation(event.target.value) }} /></label>
    </div>
    <button className={button + ' self-start text-emerald-400'} disabled={busy || loading || !data.history.length || !note.trim()}>{t(busy ? 'journal.saving' : 'journal.save')}</button>
    {success && <p role="status" className="text-sm text-emerald-400">{t('journal.saved')}</p>}
    {error && <ErrorNotice code={error} />}
  </form>
}

function Comparison({ entry }: { entry: JournalEntry }) {
  const { t } = useTranslation()
  const { data, loading, error } = useStockDetail(entry.ticker, undefined, entry.snapshot.interval)
  const current = data?.ticker.toUpperCase() === entry.ticker.toUpperCase() ? data : null
  const last = current?.history[current.history.length - 1]
  const prior = entry.snapshot.history[entry.snapshot.history.length - 1]
  const comparable = last && current?.currency === entry.snapshot.currency && Date.parse(last.time) > Date.parse(prior.time)
  return <div className="mt-4">
    <h4 className="font-medium">{t('journal.currentChart')}</h4>
    {loading && <p role="status">{t('journal.loading')}</p>}
    {error && <p role="alert" className="text-rose-400">{t('journal.compareFailed')}</p>}
    {current && <>
      {comparable ? <p className="my-2 text-sm">{fmtMoney(entry.snapshot.referencePrice, entry.snapshot.currency)} → {fmtMoney(last.close, entry.snapshot.currency)} ({fmtPct((last.close / entry.snapshot.referencePrice - 1) * 100)}) · {last.time}</p> : <p className="my-2 text-sm text-slate-400">{t('journal.noLaterData')}</p>}
      <p className="text-xs text-slate-500">{t('journal.priceNote')}</p>
      <div className="h-[300px]"><StockChart candles={current.history} signals={[]} /></div>
    </>}
  </div>
}

function EntryDetail({ id, changed, removed }: { id: string; changed: (entry: JournalEntry) => void; removed: () => void }) {
  const { t, i18n } = useTranslation()
  const [entry, setEntry] = useState<JournalEntry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<JournalStatus>('observing')
  const [review, setReview] = useState('')
  const [compare, setCompare] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const mutation = useRef<AbortController | null>(null)
  useEffect(() => () => mutation.current?.abort(), [])
  useEffect(() => {
    const abort = new AbortController()
    setError(null)
    journalRequest<JournalEntry>('GET', `/${id}`, undefined, abort.signal).then((result) => {
      if (!abort.signal.aborted) { setEntry(result); setReview(result.review); setStatus(result.status) }
    }).catch((failure: unknown) => { if (!abort.signal.aborted) setError(errorCode(failure)) })
    return () => abort.abort()
  }, [id, revision])

  async function update(remove = false) {
    if (!entry || mutation.current) return
    const abort = new AbortController()
    mutation.current = abort
    setBusy(true); setError(null)
    try {
      if (remove) {
        await journalRequest('DELETE', `/${id}?version=${entry.version}`, undefined, abort.signal)
        if (!abort.signal.aborted) removed()
      } else {
        const result = await journalRequest<JournalEntry>('PATCH', `/${id}`, { version: entry.version, status, review }, abort.signal)
        if (!abort.signal.aborted) { setEntry(result); changed(result) }
      }
    } catch (failure) { if (!abort.signal.aborted) setError(errorCode(failure)) }
    finally { if (!abort.signal.aborted) { mutation.current = null; setBusy(false) } }
  }

  return <div className="mt-3 flex flex-col gap-3 border-t border-slate-800 pt-3">
    {error && <ErrorNotice code={error} retry={() => setRevision((value) => value + 1)} />}
    {!entry && !error && <p role="status">{t('journal.loading')}</p>}
    {entry && <>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="text-slate-400">{t('journal.confirmation')}</dt><dd className="whitespace-pre-wrap break-words">{entry.confirmation || '—'}</dd></div>
        <div><dt className="text-slate-400">{t('journal.invalidation')}</dt><dd className="whitespace-pre-wrap break-words">{entry.invalidation || '—'}</dd></div>
      </dl>
      <h4 className="font-medium">{t('journal.savedChart')} · {entry.snapshot.interval} · {entry.snapshot.currency}</h4>
      <p className="text-xs text-slate-400">{t('journal.frozenHint')} {entry.snapshot.history[0].time} – {entry.snapshot.history[entry.snapshot.history.length - 1].time}</p>
      <div className="flex flex-wrap gap-3 text-sm">
        <span>{t('journal.combined')}: {entry.snapshot.combinedScore?.toFixed(1) ?? '—'}/100</span>
        {entry.snapshot.rating !== null && <span>VSA: {entry.snapshot.rating}/100</span>}
        {entry.snapshot.ratingSession && <span>{t('journal.ratingSession')}: {entry.snapshot.ratingSession}</span>}
        {entry.snapshot.methodScores.map((method) => <span key={method.methodId} title={method.detail ?? undefined}>{method.methodId}: {method.score?.toFixed(1) ?? '—'}</span>)}
      </div>
      <div className="h-[300px]"><StockChart candles={entry.snapshot.history} signals={[]} overlays={entry.snapshot.overlays} /></div>
      <button className={button + ' self-start'} aria-expanded={compare} onClick={() => setCompare((value) => !value)}>{t(compare ? 'journal.hideComparison' : 'journal.compare')}</button>
      {compare && <Comparison entry={entry} />}
      <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void update() }}>
        <label className="text-sm">{t('journal.status')}<select className={input} value={status} disabled={busy} onChange={(event) => setStatus(event.target.value as JournalStatus)}>{statuses.map((value) => <option key={value} value={value}>{t(`journal.statuses.${value}`)}</option>)}</select></label>
        <label className="text-sm">{t('journal.review')}<textarea className={input} value={review} rows={3} maxLength={5000} disabled={busy} onChange={(event) => setReview(event.target.value)} /></label>
        <div className="flex flex-wrap gap-2"><button className={button} disabled={busy}>{t(busy ? 'journal.saving' : 'journal.saveReview')}</button><button type="button" className={button} disabled={busy} onClick={() => setDeleting(true)}>{t('journal.delete')}</button></div>
        <p className="text-xs text-slate-500">{t('journal.updated')}: {new Date(entry.updatedAt).toLocaleString(i18n.language)}</p>
      </form>
      {deleting && <div className="flex flex-wrap items-center gap-2 text-sm"><span>{t('journal.confirmDelete')}</span><button className={button} disabled={busy} onClick={() => { void update(true) }}>{t('journal.confirm')}</button><button className={button} onClick={() => setDeleting(false)}>{t('journal.cancel')}</button></div>}
    </>}
  </div>
}

function AccountJournal(props: Props) {
  const { t, i18n } = useTranslation()
  const [page, setPage] = useState(0)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<JournalPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const refresh = () => setRevision((value) => value + 1)
  useEffect(() => {
    const abort = new AbortController()
    const params = new URLSearchParams({ offset: String(page * 20), limit: '20' })
    if (props.ticker) params.set('ticker', props.ticker)
    setError(null); setResult(null)
    journalRequest<JournalPage>('GET', `?${params}`, undefined, abort.signal).then((data) => {
      if (!abort.signal.aborted) {
        if (!data.items.length && page > 0) setPage((value) => value - 1)
        else setResult(data)
      }
    }).catch((failure: unknown) => { if (!abort.signal.aborted) setError(errorCode(failure)) })
    return () => abort.abort()
  }, [props.ticker, page, revision])
  return <div className="flex flex-col gap-4">
    {props.data && <Composer {...props} data={props.data} loading={props.loading || props.data.ticker.toUpperCase() !== props.ticker?.toUpperCase()} saved={() => { setPage(0); refresh() }} />}
    <div className="flex items-center justify-between gap-2"><p className="text-sm text-slate-400">{t(props.ticker ? 'journal.stockEntries' : 'journal.allEntries')}</p><button className={button} onClick={refresh}>{t('journal.refresh')}</button></div>
    {error && <ErrorNotice code={error} retry={refresh} />}
    {!result && !error && <p role="status">{t('journal.loading')}</p>}
    {result?.items.length === 0 && <p className="py-4 text-sm text-slate-400">{t('journal.empty')}</p>}
    {result?.items.map((entry) => <article key={entry.id} className="rounded-lg border border-slate-800 p-4">
      <div className="flex flex-wrap items-center gap-3 text-sm"><Link className="font-semibold text-emerald-400" to={`/stock/${encodeURIComponent(entry.ticker.toLowerCase())}`}>{entry.ticker}</Link><time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString(i18n.language)}</time><span className="rounded bg-slate-800 px-2 py-1">{t(`journal.statuses.${entry.status}`)}</span></div>
      <p className="my-3 whitespace-pre-wrap break-words text-sm">{entry.note}</p>
      <button className={button} aria-expanded={expanded === entry.id} onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}>{t(expanded === entry.id ? 'journal.hide' : 'journal.open')}</button>
      {expanded === entry.id && <EntryDetail id={entry.id} changed={(updated) => {
        setResult((previous) => previous ? { ...previous, items: previous.items.map((item) => item.id === updated.id ? updated : item) } : previous)
      }} removed={() => { setExpanded(null); refresh() }} />}
    </article>)}
    {result && result.total > 20 && <div className="flex items-center gap-3 text-sm"><button className={button} disabled={page === 0} onClick={() => { setExpanded(null); setPage((value) => value - 1) }}>{t('journal.previous')}</button><span>{page + 1} / {Math.ceil(result.total / 20)}</span><button className={button} disabled={(page + 1) * 20 >= result.total} onClick={() => { setExpanded(null); setPage((value) => value + 1) }}>{t('journal.next')}</button></div>}
  </div>
}

export function JournalPanel(props: Props) {
  const { t } = useTranslation()
  const { user, loading, config } = useAuth()
  return <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-slate-200">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">{t('journal.title')}</h2>{props.ticker && <Link className="text-sm text-emerald-400" to="/journal">{t('journal.allEntries')}</Link>}</div>
    {loading ? <p role="status">{t('journal.loading')}</p> : user ? <AccountJournal key={`${user.id}:${props.ticker ?? '*'}`} {...props} /> : <p className="text-sm text-slate-400">{t('journal.accountOnly')} {config?.enabled !== false && <Link className="text-emerald-400" to="/login">{t('journal.signIn')}</Link>}</p>}
  </section>
}
