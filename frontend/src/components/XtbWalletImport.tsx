import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../api/client'
import { importXtbWallets, previewXtbWallets, type Portfolio, type XtbWalletsImportResult, type XtbWalletsPreview } from '../api/portfoliosApi'
import { currencyLabel } from '../lib/format'
import { XtbPreviewTable } from './XtbPreviewTable'

const button = 'rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40'
const MAX_BYTES = 5 * 1024 * 1024

export function XtbWalletImport({ owner, portfolios = [], disabled, onImported, onBusyChange }: {
  owner: number; disabled: boolean; onImported: () => Promise<void>; onBusyChange?: (busy: boolean) => void
  portfolios?: Pick<Portfolio, 'id' | 'name' | 'broker' | 'brokerAccountId' | 'brokerAccountCurrency'>[]
}) {
  const { t } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const [targetWalletId, setTargetWalletId] = useState('')
  const [preview, setPreview] = useState<XtbWalletsPreview | null>(null)
  const [result, setResult] = useState<(XtbWalletsImportResult & { linkedAccount: boolean; savedCurrency: boolean }) | null>(null)
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
  const targetUnavailable = targetWalletId !== '' && !portfolios.some(wallet => wallet.id === targetWalletId)
  const blocked = !!preview && (!!preview.blockingError || preview.wallets.some(wallet => wallet.error || wallet.ledgerError))
  const linksAccount = !!preview?.wallets.some(wallet => wallet.linksBrokerAccount)
  const setsCurrency = !!preview?.wallets.some(wallet => wallet.setsBrokerAccountCurrency)
  const hasChanges = !!preview && (!!preview.newWallets || !!preview.ready || linksAccount || setsCurrency)
  const canImport = hasChanges && !blocked && (!preview.errors || allowPartial)
  let confirmLabel = t(setsCurrency ? 'portfolio.xtbWallets.confirmDetails' : 'portfolio.xtbWallets.confirmLinks')
  if (preview?.newWallets) {
    const updatesExisting = preview.wallets.some(wallet =>
      wallet.version !== null && (wallet.ready > 0 || wallet.linksBrokerAccount || wallet.setsBrokerAccountCurrency),
    )
    confirmLabel = updatesExisting
      ? t('portfolio.xtbWallets.confirmMixed')
      : preview.newWallets === 1
        ? t('portfolio.xtbWallets.confirmOne')
        : t('portfolio.xtbWallets.confirm', { count: preview.newWallets })
  } else if (preview?.ready) {
    confirmLabel = t('portfolio.xtbWallets.confirmTrades', { count: preview.ready })
  }

  function clearPreview() {
    setPreview(null)
    setAllowPartial(false)
  }

  async function run(approval?: XtbWalletsPreview) {
    if (!file || request.current || disabled || targetUnavailable || (approval && !canImport)) return
    const abort = new AbortController()
    request.current = abort
    setBusy(true)
    onBusyChange?.(true)
    setError(null)
    setResult(null)
    if (!approval) clearPreview()
    try {
      if (approval) {
        const saved = await importXtbWallets(file, owner, approval.previewToken, allowPartial, abort.signal, targetWalletId || undefined)
        if (abort.signal.aborted) return
        setResult({ ...saved, linkedAccount: linksAccount, savedCurrency: setsCurrency })
        clearPreview()
        await onImported()
      } else {
        const next = await previewXtbWallets(file, owner, abort.signal, targetWalletId || undefined)
        if (!abort.signal.aborted) setPreview(next)
      }
    } catch (failure) {
      if (!abort.signal.aborted) {
        const code = failure instanceof ApiError && failure.code ? failure.code : 'failed'
        setError(code)
        if (['import_preview_changed', 'account_changed', 'conflict', 'not_found',
          'broker_account_mismatch', 'broker_account_already_linked', 'broker_account_currency_mismatch'].includes(code)) {
          clearPreview()
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

  let resultLabel = ''
  if (result) {
    if (result.created || result.imported) resultLabel = t('portfolio.xtbWallets.saved', { ...result })
    else if (result.savedCurrency) resultLabel = t('portfolio.xtbWallets.detailsSaved')
    else resultLabel = t(result.linkedAccount ? 'portfolio.xtbWallets.linked' : 'portfolio.xtbWallets.alreadyImported')
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
            clearPreview(); setResult(null); setError(null)
            if (selected && selected.size > MAX_BYTES) { setFile(null); setError('import_file_too_large') }
            else setFile(selected)
          }} />
      </label>
      {(portfolios.length > 0 || targetUnavailable) && <label className="min-w-0 text-sm">{t('portfolio.xtbWallets.destination')}
        <select value={targetWalletId} disabled={disabled || busy}
          className="mt-1 block w-full max-w-md rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"
          onChange={event => { setTargetWalletId(event.target.value); clearPreview(); setResult(null); setError(null) }}>
          <option value="">{t('portfolio.xtbWallets.autoMatch')}</option>
          {targetUnavailable && <option value={targetWalletId} disabled>{t('portfolio.xtbWallets.unavailableWallet')}</option>}
          {portfolios.map(wallet => <option key={wallet.id} value={wallet.id}>
            {wallet.name} · {wallet.broker}{wallet.brokerAccountId ? ` · ${wallet.brokerAccountId}` : ''}
            {wallet.brokerAccountCurrency ? ` · ${currencyLabel(wallet.brokerAccountCurrency)}` : ''}
          </option>)}
        </select>
      </label>}
      <button type="button" className={button} disabled={!file || disabled || busy || targetUnavailable} onClick={() => void run()}>{t(busy ? 'portfolio.xtb.working' : 'portfolio.xtbWallets.preview')}</button>
    </div>
    {targetUnavailable && <p role="alert" className="mt-3 text-sm text-amber-400">{t('portfolio.xtbWallets.destinationRemoved')}</p>}
    {error && <p role="alert" className="mt-3 text-sm text-rose-400">{message(error)}</p>}
    {resultLabel && <p role="status" className="mt-3 text-sm text-emerald-400">{resultLabel}</p>}
    {preview && !targetUnavailable && <div className="mt-4 space-y-3">
      <p className="text-sm">{t('portfolio.xtbWallets.summary', { count: preview.newWallets, ready: preview.ready, errors: preview.errors })}</p>
      {preview.blockingError && <p role="alert" className="text-sm text-rose-400">{message(preview.blockingError)}</p>}
      {!!preview.skippedSheets?.length && <p className="text-sm text-slate-400">
        {t('portfolio.xtbWallets.skippedSheets', { sheets: preview.skippedSheets.join(', ') })}
      </p>}
      {!blocked && !hasChanges && <p role="status" className="text-sm text-slate-400">{t(
        !preview.skippedSheets?.length && preview.wallets.some(wallet => wallet.duplicates > 0)
          ? 'portfolio.xtbWallets.alreadyImported' : 'portfolio.xtbWallets.noNewTrades',
      )}</p>}
      {preview.wallets.map(wallet => <details key={wallet.id} className="rounded-lg border border-slate-800 p-3" open={
        !!wallet.error || !!wallet.ledgerError || !!wallet.errors ||
        (wallet.version === null && !wallet.ready) || wallet.warnings.includes('xtb_reconciliation_unavailable')
      }>
        <summary className="cursor-pointer text-sm font-medium">
          {wallet.name} — {t('portfolio.xtb.summary', { ready: wallet.ready, duplicates: wallet.duplicates, errors: wallet.errors })}
          <span className="ml-2 whitespace-nowrap text-slate-400">{t(wallet.version === null ? 'portfolio.xtbWallets.newWallet' : 'portfolio.xtbWallets.walletExists')}</span>
          {(wallet.brokerAccountId || wallet.sourceBrokerAccountId) && <span className="ml-2 whitespace-nowrap text-slate-400">
            {wallet.brokerAccountId
              ? t('portfolio.brokerAccountIdValue', { id: wallet.brokerAccountId })
              : t('portfolio.xtbWallets.sourceAccount', { id: wallet.sourceBrokerAccountId })}
          </span>}
          {(wallet.brokerAccountCurrency || wallet.sourceBrokerAccountCurrency) && <span className="ml-2 whitespace-nowrap text-slate-400">
            {t(wallet.brokerAccountCurrency ? 'portfolio.xtbWallets.accountCurrency' : 'portfolio.xtbWallets.reportCurrency', {
              currency: currencyLabel(wallet.brokerAccountCurrency || wallet.sourceBrokerAccountCurrency),
            })}
          </span>}
        </summary>
        <div className="mt-3 space-y-2">
          {wallet.error && <p role="alert" className="text-sm text-rose-400">{message(wallet.error)}</p>}
          {wallet.ledgerError && <p role="alert" className="text-sm text-rose-400">{message(wallet.ledgerError)}</p>}
          {wallet.version === null && !wallet.ready && !wallet.error && !wallet.ledgerError && <p className="text-xs text-slate-400">{t('portfolio.xtbWallets.emptyWallet')}</p>}
          {!!wallet.ignored && <p className="text-xs text-slate-400">{t('portfolio.xtb.ignored', { count: wallet.ignored })}</p>}
          {wallet.warnings.map(code => <p key={code} className="text-sm text-amber-400">{message(code)}</p>)}
          {!!wallet.rows.length && <XtbPreviewTable rows={wallet.rows} message={message} />}
        </div>
      </details>)}
      {!blocked && hasChanges && !!preview.errors && <label className="flex items-start gap-2 text-sm text-amber-400"><input type="checkbox" checked={allowPartial} disabled={busy || disabled} onChange={event => setAllowPartial(event.target.checked)} />{t('portfolio.xtb.partial')}</label>}
      {hasChanges && <button type="button" className={button + ' text-emerald-400'} disabled={busy || disabled || !canImport} onClick={() => void run(preview)}>
        {confirmLabel}
      </button>}
    </div>}
  </section>
}
