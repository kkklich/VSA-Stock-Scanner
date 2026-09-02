// "Investment (capex)" card for the stock-detail page — the single-stock view of
// the /capex screen. Shows how much the company invests in its own business
// (plants, machines, software), how that compares to last year, and how it sits
// against revenue and the cash the business itself generates. Data is the same
// `capex` summary the fundamentals endpoint already returns (so this card and
// the /capex page never disagree); it is passed in from the page, which fetches
// fundamentals once and shares it with the Fundamentals card.

import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import type { ApiFundamentals } from '../api/stocksApi'
import { Card, CardTitle, InfoTip } from './ui'
import { deltaTone, fmtCompactPln, fmtPct } from '../lib/format'

export function InvestmentCard({
  data,
  loading,
}: {
  data: ApiFundamentals | null
  loading: boolean
}) {
  const { t } = useTranslation()
  const capex = data?.capex ?? null

  // Figures are in the statement's own reporting currency — not always PLN for
  // dual-listed foreign issuers.
  const currency = capex?.currency ?? 'PLN'
  const money = (v: number | null | undefined) =>
    v == null ? '—' : `${fmtCompactPln(v)} ${currency}`
  const pct0 = (v: number | null | undefined) =>
    v == null ? '—' : `${v.toFixed(0)}%`
  const pct1 = (v: number | null | undefined) =>
    v == null ? '—' : `${v.toFixed(1)}%`

  return (
    <Card>
      <CardTitle>
        {t('chart.fundamentals.investment')}{' '}
        <InfoTip text={t('chart.fundamentals.investmentInfo')} />
      </CardTitle>
      <div className="px-4 pb-4">
        {loading && !data ? (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <Loader2 size={14} className="animate-spin" /> {t('common.loading')}
          </div>
        ) : !capex || capex.capex == null ? (
          <p className="py-2 text-sm text-slate-500">
            {t('chart.fundamentals.noInvestmentData')}
          </p>
        ) : (
          <>
            <div className="flex items-end gap-2">
              <span className="text-3xl font-bold tabular-nums text-slate-100">
                {fmtCompactPln(capex.capex)}
              </span>
              <span className="mb-1 text-xs text-slate-500">{currency}</span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {capex.basis === 'annual'
                ? t('chart.fundamentals.investedLastYear')
                : t('chart.fundamentals.invested12m')}
            </p>

            <dl className="mt-3 space-y-2 text-sm">
              <Row
                label={t('chart.fundamentals.operatingCashFlow')}
                value={money(capex.operatingCashFlow)}
              />
              <Row
                label={t('chart.fundamentals.vsPreviousYear')}
                value={
                  capex.capexGrowthYoyPct == null ? (
                    '—'
                  ) : (
                    <span className={'tabular-nums ' + deltaTone(capex.capexGrowthYoyPct)}>
                      {fmtPct(capex.capexGrowthYoyPct)}
                    </span>
                  )
                }
              />
              <Row
                label={t('chart.fundamentals.pctOfRevenue')}
                value={pct1(capex.capexToRevenuePct)}
              />
              <Row
                label={t('chart.fundamentals.pctOfCashFlow')}
                value={pct0(capex.capexToOcfPct)}
              />
            </dl>
          </>
        )}
      </div>
    </Card>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-200">{value}</dd>
    </div>
  )
}
