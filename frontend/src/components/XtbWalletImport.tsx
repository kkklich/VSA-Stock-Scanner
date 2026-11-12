import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { importXtbWallets, previewXtbWallets, type XtbWalletsImportResult, type XtbWalletsPreview } from '../api/portfoliosApi'
import { currencyLabel } from '../lib/format'
import { XtbReconciliationDetails } from './XtbReconciliationDetails'

const button = 'rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40'
const MAX_BYTES = 5 * 1024 * 1024

export function XtbWalletImport({ owner, disabled, onImported, onBusyChange }: {
  owner: number; disabled: boolean; onImported: () => Promise<void>; onBusyChange?: (busy: boolean) => void
}) {
  const { t, i18n } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<XtbWalletsPreview | null>(null)
  const [result, setResult] = useState<(XtbWalletsImportResult & { linkedAccount: boolean }) | null>(null)
  const [allowPartial, setAllowPartial] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  const message = (code: string) => t(`portfolio.xtbWallets.codes.${code}`, {
    defaultValue: t(`portfolio.errors.${code}`, {
      defaultValue: t(`portfolio.xtb.codes.${code}`, { defaultValue: t('portfolio.errors.failed') }),
    }),
  })
  const formatter = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 })
  const number = (value: string) => formatter.format(Number(value))
  const blocked = !!preview && (!!preview.blockingError || preview.wallets.some(wallet => wallet.error || wallet.ledgerError))
  const hasChanges = !!preview && (!!preview.newWallets || preview.wallets.some(wallet => wallet.linksBrokerAccount))
  const canImport = hasChanges && !blocked && (!preview.errors || allowPartial)
  async function run(approval?: XtbWalletsPreview) {
    if (!file || request.current || disabled || (approval && !canImport)) return
    const abort = new AbortController()
    request.current = abort
    setBusy(true)
    onBusyChange?.(true)
    setError(null)
    setResult(null)
    if (!approval) {
      setPreview(null)
      setAllowPartial(false)
    }
    try {
      if (approval) {
        const saved = await importXtbWallets(file, owner, approval.previewToken, allowPartial, abort.signal)
        if (abort.signal.aborted) return
        setResult({ ...saved, linkedAccount: approval.wallets.some(wallet => wallet.linksBrokerAccount) })
        setPreview(null)
        setAllowPartial(false)
        await onImported()
      } else {
        const next = await previewXtbWallets(file, owner, abort.signal)
        if (!abort.signal.aborted) setPreview(next)
      }
    } catch (failure) {
      if (!abort.signal.aborted) {
        const code = failure instanceof ApiError && failure.code ? failure.code : 'failed'
        setError(code)
        if (code === 'import_preview_changed' || code === 'account_changed') {
          setPreview(null)
          setAllowPartial(false)
        }
      }
    } finally {
      if (!abort.signal.aborted) {
        setBusy(false)
        request.current = null
        onBusyChange?.(false)
      }
    }
  }

  return <section className="rounded-xl border border-slate-800 p-4">
    <h2 className="mb-2 font-semibold">{t('portfolio.xtbWallets.title')}</h2>
    <p className="mb-3 text-sm text-slate-400">{t('portfolio.xtbWallets.hint')}</p>
    <div className="flex flex-wrap items-end gap-3">
      <label className="min-w-0 text-sm">{t('portfolio.xtbWallets.file')}
        <input type="file" accept=".xlsx,.xls,.csv" disabled={disabled || busy}
          className="mt-1 block w-full max-w-md rounded-md border border-slate-700 p-2 text-sm"
          onChange={event => {
            const selected = event.target.files?.[0] ?? null
            setPreview(null); setResult(null); setAllowPartial(false); setError(null)
            if (selected && selected.size > MAX_BYTES) { setFile(null); setError('import_file_too_large') }
            else setFile(selected)
          }} />
      </label>
      <button type="button" className={button} disabled={!file || disabled || busy} onClick={() => void run()}>{t(busy ? 'portfolio.xtb.working' : 'portfolio.xtbWallets.preview')}</button>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-rose-400">{message(error)}</p>}
    {result && <p role="status" className="mt-3 text-sm text-emerald-400">
      {result.created ? t('portfolio.xtbWallets.saved', { ...result }) : t(result.linkedAccount ? 'portfolio.xtbWallets.linked' : 'portfolio.xtbWallets.alreadyImported')}
    </p>}
    {preview && <div className="mt-4 space-y-3">
      <p className="text-sm">{t('portfolio.xtbWallets.summary', { count: preview.newWallets, ready: preview.ready, errors: preview.errors })}</p>
      {preview.blockingError && <p role="alert" className="text-sm text-rose-400">{message(preview.blockingError)}</p>}
      {!blocked && !hasChanges && <p role="status" className="text-sm text-emerald-400">{t('portfolio.xtbWallets.alreadyImported')}</p>}
      {preview.wallets.map(wallet => <details key={wallet.id} className="rounded-lg border border-slate-800 p-3" open={
        !!wallet.error || !!wallet.ledgerError || !!wallet.errors || !!wallet.reconciliation ||
        (wallet.version === null && !wallet.ready) || wallet.warnings.includes('xtb_reconciliation_unavailable')
      }>
        <summary className="cursor-pointer text-sm font-medium">
          {wallet.name} — {t('portfolio.xtb.summary', { ready: wallet.ready, duplicates: wallet.duplicates, errors: wallet.errors })}
          {(wallet.brokerAccountId || wallet.sourceBrokerAccountId) && <span className="ml-2 whitespace-nowrap text-slate-400">
            {wallet.brokerAccountId
              ? t('portfolio.brokerAccountIdValue', { id: wallet.brokerAccountId })
              : t('portfolio.xtbWallets.sourceAccount', { id: wallet.sourceBrokerAccountId })}
          </span>}
        </summary>
        <div className="mt-3 space-y-2">
          {wallet.error && <p role="alert" className="text-sm text-rose-400">{message(wallet.error)}</p>}
          {wallet.ledgerError && <p role="alert" className="text-sm text-rose-400">{message(wallet.ledgerError)}</p>}
          {wallet.version !== null && <p className="text-xs text-slate-400">{t('portfolio.xtbWallets.walletExists')}</p>}
          {wallet.version === null && !wallet.ready && !wallet.error && !wallet.ledgerError && <p className="text-xs text-slate-400">{t('portfolio.xtbWallets.emptyWallet')}</p>}
          {!!wallet.ignored && <p className="text-xs text-slate-400">{t('portfolio.xtb.ignored', { count: wallet.ignored })}</p>}
          {wallet.warnings.map(code => <p key={code} className="text-sm text-amber-400">{message(code)}</p>)}
          {wallet.reconciliation && <XtbReconciliationDetails reconciliation={wallet.reconciliation} />}
          {!!wallet.rows.length && <div className="max-h-80 overflow-auto rounded-md border border-slate-800">
            <table className="w-full whitespace-nowrap text-left text-xs">
              <thead className="sticky top-0 bg-slate-950 text-slate-400"><tr>{['source', 'date', 'side', 'instrument', 'quantity', 'price', 'fees', 'status'].map(key => <th key={key} className="p-2">{t(['source', 'status'].includes(key) ? `portfolio.xtb.${key}` : `portfolio.${key}`)}</th>)}</tr></thead>
              <tbody>{wallet.rows.map((row, index) => {
                const trade = row.transaction
                const amount = (value: string) => `${number(value)} ${currencyLabel(trade?.currency)}`
                return <tr key={`${row.row}:${index}`} className="border-t border-slate-800">
                  <td className="p-2">{row.sheet} · {row.row}</td><td className="p-2">{trade?.executedAt?.replace('T', ' ') ?? trade?.date ?? '—'}</td>
                  <td className="p-2">{trade ? t(`portfolio.${trade.side}`) : '—'}</td><td className="p-2">{trade?.ticker.toUpperCase() ?? row.symbol}</td>
                  <td className="p-2">{trade ? number(trade.quantity) : '—'}</td><td className="p-2">{trade ? amount(trade.price) : '—'}</td><td className="p-2">{trade ? amount(trade.fees) : '—'}</td>
                  <td className={'p-2 ' + (row.status === 'error' ? 'text-amber-400' : 'text-slate-300')}>{row.code ? message(row.code) : t(`portfolio.xtb.${row.status}`)}</td>
                </tr>
              })}</tbody>
            </table>
          </div>}
        </div>
      </details>)}
      {!blocked && hasChanges && !!preview.errors && <label className="flex items-start gap-2 text-sm text-amber-400"><input type="checkbox" checked={allowPartial} disabled={busy || disabled} onChange={event => setAllowPartial(event.target.checked)} />{t('portfolio.xtb.partial')}</label>}
      {!!preview.newWallets && <p className="text-xs text-slate-400">{t('portfolio.xtbWallets.reconcile')}</p>}
      {hasChanges && <button type="button" className={button + ' text-emerald-400'} disabled={busy || disabled || !canImport} onClick={() => void run(preview)}>
        {preview.newWallets ? t('portfolio.xtbWallets.confirm', { count: preview.newWallets }) : t('portfolio.xtbWallets.confirmLinks')}
      </button>}
    </div>}
  </section>
}
