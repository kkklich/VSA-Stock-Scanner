import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { importXtb, previewXtb, type Portfolio, type XtbImportResult, type XtbPreview } from '../api/portfoliosApi'
import { currencyLabel } from '../lib/format'

const button = 'rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40'
const MAX_BYTES = 5 * 1024 * 1024

export function XtbImport({ owner, portfolio, disabled, onImported }: {
  owner: number; portfolio: Portfolio; disabled: boolean; onImported: () => Promise<void>
}) {
  const { t, i18n } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<XtbPreview | null>(null)
  const [result, setResult] = useState<XtbImportResult | null>(null)
  const [allowPartial, setAllowPartial] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  const message = (code: string) => t(`portfolio.xtb.codes.${code}`, { defaultValue: t('portfolio.errors.failed') })
  const number = (value: string) => Number(value).toLocaleString(i18n.language, { maximumFractionDigits: 8 })
  async function run(commit: boolean) {
    if (!file || request.current || disabled) return
    const abort = new AbortController()
    request.current = abort
    setBusy(true); setError(null); setResult(null)
    try {
      if (commit && preview) {
        const saved = await importXtb(portfolio.id, file, preview.version, allowPartial, abort.signal, owner)
        if (abort.signal.aborted) return
        setResult(saved); setPreview(null); setAllowPartial(false)
        await onImported()
      } else {
        const next = await previewXtb(portfolio.id, file, abort.signal, owner)
        if (!abort.signal.aborted) { setPreview(next); setAllowPartial(false) }
      }
    } catch (failure) {
      if (!abort.signal.aborted) {
        const code = failure instanceof ApiError && failure.code ? failure.code : 'failed'
        setError(code)
        if (code === 'account_changed') {
          setPreview(null)
          setAllowPartial(false)
        }
      }
    } finally {
      if (!abort.signal.aborted) { setBusy(false); request.current = null }
    }
  }

  const versionChanged = !!preview && preview.version !== portfolio.version
  return <section className="rounded-xl border border-slate-800 p-4">
    <h3 className="mb-2 font-semibold">{t('portfolio.xtb.title')}</h3>
    <p className="mb-3 text-sm text-slate-400">{t('portfolio.xtb.hint')}</p>
    <div className="flex flex-wrap items-end gap-3">
      <label className="min-w-0 text-sm">{t('portfolio.xtb.file')}
        <input type="file" accept=".xlsx,.xls,.csv" disabled={disabled || busy}
          className="mt-1 block w-full max-w-md rounded-md border border-slate-700 p-2 text-sm"
          onChange={event => {
            const selected = event.target.files?.[0] ?? null
            setPreview(null); setResult(null); setAllowPartial(false); setError(null)
            if (selected && selected.size > MAX_BYTES) { setFile(null); setError('import_file_too_large') }
            else setFile(selected)
          }} />
      </label>
      <button type="button" className={button} disabled={!file || disabled || busy} onClick={() => void run(false)}>{t(busy ? 'portfolio.xtb.working' : 'portfolio.xtb.preview')}</button>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-rose-400">{t(`portfolio.errors.${error}`, { defaultValue: message(error) })}</p>}
    {result && <p role="status" className="mt-3 text-sm text-emerald-400">{t('portfolio.xtb.saved', { ...result })}</p>}
    {preview && <div className="mt-4 space-y-3">
      <p className="text-sm">{t('portfolio.xtb.summary', { ready: preview.ready, duplicates: preview.duplicates, errors: preview.errors })}</p>
      {!!preview.ignored && <p className="text-xs text-slate-400">{t('portfolio.xtb.ignored', { count: preview.ignored })}</p>}
      {preview.warnings.map(code => <p key={code} className="text-sm text-amber-400">{message(code)}</p>)}
      {preview.ledgerError && <p role="alert" className="text-sm text-rose-400">{t(`portfolio.errors.${preview.ledgerError}`, { defaultValue: message(preview.ledgerError) })}</p>}
      {versionChanged && <p role="alert" className="text-sm text-amber-400">{t('portfolio.xtb.changed')}</p>}
      <div className="max-h-80 overflow-auto rounded-md border border-slate-800">
        <table className="w-full whitespace-nowrap text-left text-xs">
          <thead className="sticky top-0 bg-slate-950 text-slate-400"><tr>{['source', 'date', 'side', 'instrument', 'quantity', 'price', 'fees', 'status'].map(key => <th key={key} className="p-2">{t(['source', 'status'].includes(key) ? `portfolio.xtb.${key}` : `portfolio.${key}`)}</th>)}</tr></thead>
          <tbody>{preview.rows.map((row, index) => {
            const trade = row.transaction
            const amount = (value: string) => `${number(value)} ${currencyLabel(trade?.currency)}`
            return <tr key={`${row.sheet}:${row.row}:${index}`} className="border-t border-slate-800">
              <td className="p-2">{row.sheet} · {row.row}</td><td className="p-2">{trade?.executedAt?.replace('T', ' ') ?? trade?.date ?? '—'}</td>
              <td className="p-2">{trade ? t(`portfolio.${trade.side}`) : '—'}</td><td className="p-2">{trade?.ticker.toUpperCase() ?? row.symbol}</td>
              <td className="p-2">{trade ? number(trade.quantity) : '—'}</td><td className="p-2">{trade ? amount(trade.price) : '—'}</td><td className="p-2">{trade ? amount(trade.fees) : '—'}</td>
              <td className={'p-2 ' + (row.status === 'error' ? 'text-amber-400' : 'text-slate-300')}>{row.code ? message(row.code) : t(`portfolio.xtb.${row.status}`)}</td>
            </tr>
          })}</tbody>
        </table>
      </div>
      {!!preview.errors && <label className="flex items-start gap-2 text-sm text-amber-400"><input type="checkbox" checked={allowPartial} disabled={busy || disabled} onChange={event => setAllowPartial(event.target.checked)} />{t('portfolio.xtb.partial')}</label>}
      <p className="text-xs text-slate-400">{t('portfolio.xtb.reconcile')}</p>
      <button type="button" className={button + ' text-emerald-400'} disabled={busy || disabled || !preview.ready || !!preview.ledgerError || versionChanged || (!!preview.errors && !allowPartial)} onClick={() => void run(true)}>{t('portfolio.xtb.confirm', { count: preview.ready, name: portfolio.name })}</button>
    </div>}
  </section>
}
