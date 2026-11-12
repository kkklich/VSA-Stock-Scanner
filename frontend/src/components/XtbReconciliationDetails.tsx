import { useTranslation } from 'react-i18next'
import type { XtbReconciliation } from '../api/portfoliosApi'
import { currencyLabel } from '../lib/format'

export function XtbReconciliationDetails({ reconciliation }: { reconciliation: XtbReconciliation }) {
  const { t, i18n } = useTranslation()
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 })
  const format = (value: string) => number.format(Number(value))
  const { asOf, changes } = reconciliation

  return <section className="space-y-2 rounded-lg border border-slate-800 p-3">
    <h3 className="text-sm font-semibold">{t('portfolio.xtbWallets.reconciliation.title')}</h3>
    <p className="text-xs text-slate-400">{t('portfolio.xtbWallets.reconciliation.date', { asOf: asOf.replace('T', ' ') })}</p>
    {!!changes.length && <div className="max-h-64 overflow-auto">
      <table className="w-full whitespace-nowrap text-left text-xs">
        <thead className="sticky top-0 bg-slate-950 text-slate-400">
          <tr>
            <th scope="col" className="p-2">{t('portfolio.instrument')}</th>
            {['previousQuantity', 'quantity', 'previousCost', 'cost'].map(key =>
              <th key={key} scope="col" className="p-2">{t(`portfolio.xtbWallets.reconciliation.${key}`)}</th>)}
          </tr>
        </thead>
        <tbody>{changes.map(change => <tr key={`${change.ticker}:${change.currency}`} className="border-t border-slate-800">
          <th scope="row" className="p-2 font-medium">{change.ticker.toUpperCase()}</th>
          <td className="p-2">{format(change.previousQuantity)}</td>
          <td className="p-2">{format(change.quantity)}</td>
          <td className="p-2">{format(change.previousCost)} {currencyLabel(change.currency)}</td>
          <td className="p-2">{format(change.cost)} {currencyLabel(change.currency)}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>
}
