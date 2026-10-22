import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useFinancialHistory, useLongTermHistory } from '../hooks/useLongTerm'
import type { FinancialObservation, LongTermItem } from '../types/longTerm'
import { Card } from './ui'
import { scoreText } from '../lib/longTerm'
import { LongTermHistoryChart } from './LongTermHistoryChart'
import { LongTermFactorBar } from './LongTermFactorBar'

const INPUT_KEYS = ['roe', 'roa', 'netMargin', 'earningsYield', 'momentum12_1', 'momentum6_1'] as const

/** Preserve date-only session/report dates; localise observation timestamps. */
function timestamp(value: string | null, locale: string): string {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString(locale, { dateStyle: 'short', timeStyle: 'medium' })
}

export function LongTermInputs({ item }: { item: LongTermItem }) {
  const { t, i18n } = useTranslation()
  return (
    <div className="space-y-3 text-xs">
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {INPUT_KEYS.map((key) => <div key={key} className="min-w-0">
          <dt className="text-slate-400">{t(`longTerm.inputs.${key}`)}</dt>
          <dd className="mt-1 font-medium tabular-nums text-slate-200">
            {item.inputs[key] == null ? '—' : item.inputs[key].toLocaleString(i18n.language, { style: 'percent', maximumFractionDigits: 2 })}
          </dd>
        </div>)}
      </dl>
      {item.inputs.earningsYield === 0 && <p className="text-slate-400">{t('longTerm.lossValuationInput')}</p>}
      <p className="text-slate-400">{t('longTerm.financialObservedAt')}: {timestamp(item.fundamentalsObservedAt, i18n.language)}</p>
      <p className="text-slate-400">{t('longTerm.comparison', {
        group: t(`longTerm.groups.${item.comparisonGroup}`, { defaultValue: item.comparisonGroup }), peers: item.peerCount,
      })}</p>
      {item.missing.length > 0 && <p className="text-amber-400">{item.missing.map((key) => t(`longTerm.missing.${key}`, { defaultValue: t('longTerm.missing.unknown') })).join(' · ')}</p>}
    </div>
  )
}

export function LoadError({ retry }: { retry: () => void }) {
  const { t } = useTranslation()
  return <div role="alert" className="rounded-lg border border-rose-500/30 p-3 text-sm text-rose-400">
    {t('longTerm.loadError')}{' '}
    <button type="button" className="underline" onClick={retry}>{t('common.retry')}</button>
  </div>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

const FINANCIAL_FIELDS = [
  'periodEnd', 'periodType', 'financialCurrency', 'currency', 'marketCap', 'peRatio', 'forwardPe', 'eps',
  'dividendYield', 'totalRevenue', 'netIncome', 'operatingIncome', 'sharesOutstanding',
  'returnOnEquity', 'returnOnAssets', 'capex', 'operatingCashFlow', 'freeCashFlow',
  'lastReportDate', 'nextReportDate',
] as const
const RATIO_FIELDS = new Set(['returnOnEquity', 'returnOnAssets'])
const MONEY_FIELDS = new Set(['marketCap', 'eps', 'totalRevenue', 'netIncome', 'operatingIncome', 'capex', 'operatingCashFlow', 'freeCashFlow'])

function FinancialValues({ values, reportingCurrency }: {
  values: Record<string, unknown>
  reportingCurrency: unknown
}) {
  const { t, i18n } = useTranslation()
  return <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
    {FINANCIAL_FIELDS.filter((key) => key in values).map((key) => {
      const value = values[key]
      let formatted = '—'
      if (typeof value === 'number' && Number.isFinite(value)) {
        formatted = value.toLocaleString(i18n.language, { maximumFractionDigits: 2, ...(RATIO_FIELDS.has(key) ? { style: 'percent' } : {}) })
        // Dividend yield is archived in percentage points, unlike ROE/ROA fractions.
        if (key === 'dividendYield') formatted = (value / 100).toLocaleString(i18n.language, { style: 'percent', maximumFractionDigits: 2 })
        if (MONEY_FIELDS.has(key)) {
          // FinancialMetrics stores a reporting currency but no currency for
          // marketCap or trailing EPS. Never infer an archived quote currency
          // from today's ticker metadata or label all figures with one unit.
          const currencyKnown = key !== 'marketCap' && key !== 'eps'
            && typeof reportingCurrency === 'string' && reportingCurrency.trim() !== ''
          formatted += ` ${currencyKnown ? reportingCurrency : `(${t('longTerm.currencyUnknown')})`}`
        }
      } else if (typeof value === 'string') {
        formatted = key === 'periodType' ? t(`longTerm.periods.${value}`, { defaultValue: value }) : value
      }
      return <div key={key} className="min-w-0">
        <dt className="text-xs text-slate-400">{t(`longTerm.fields.${key}`)}</dt>
        <dd className="mt-1 break-words text-sm tabular-nums text-slate-200">{formatted}</dd>
      </div>
    })}
  </dl>
}

function FinancialPayload({ observation }: { observation: FinancialObservation }) {
  const { t } = useTranslation()
  if (observation.kind === 'fundamentals') return <FinancialValues values={observation.payload} reportingCurrency={observation.payload.financialCurrency} />
  const values = observation.kind === 'quarterly' ? observation.payload.reports : observation.payload.periods
  const periods = Array.isArray(values) ? values.filter(isRecord) : []
  return <div className="space-y-4">
    {typeof observation.payload.financialCurrency === 'string' && <p className="text-xs text-slate-400">
      {t('longTerm.quarterlyCurrencyContext', { currency: observation.payload.financialCurrency })}
    </p>}
    {periods.length === 0 && <p className="text-sm text-slate-400">{t('longTerm.noPeriods')}</p>}
    {periods.map((period, index) => <div key={index} className="rounded-lg border border-slate-800 p-3"><FinancialValues values={period} reportingCurrency={observation.kind === 'cashflow' ? period.currency : null} /></div>)}
  </div>
}

export function LongTermHistory({ item, close }: { item: LongTermItem; close: () => void }) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const tabs = ['overview', 'scores', 'financials'] as const
  type Tab = typeof tabs[number]
  const [selection, setSelection] = useState<{ ticker: string; tab: Tab }>({ ticker: item.ticker, tab: 'overview' })
  // A new stock starts at Overview before effects or network requests can run.
  const activeTab = selection.ticker === item.ticker ? selection.tab : 'overview'
  useEffect(() => {
    setSelection((current) => current.ticker === item.ticker ? current : { ticker: item.ticker, tab: 'overview' })
  }, [item.ticker])
  const tabRefs = useRef<Partial<Record<Tab, HTMLButtonElement | null>>>({})
  const scores = useLongTermHistory(activeTab === 'scores' ? item.ticker : null)
  const financials = useFinancialHistory(activeTab === 'financials' ? item.ticker : null)
  const selectTab = (tab: Tab) => setSelection({ ticker: item.ticker, tab })
  const navigateTabs = (event: KeyboardEvent<HTMLButtonElement>, tab: Tab) => {
    const index = tabs.indexOf(tab)
    let next: Tab
    if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length]
    else if (event.key === 'ArrowLeft') next = tabs[(index + tabs.length - 1) % tabs.length]
    else if (event.key === 'Home') next = tabs[0]
    else if (event.key === 'End') next = tabs[tabs.length - 1]
    else return
    event.preventDefault()
    selectTab(next)
    tabRefs.current[next]?.focus()
  }
  return <Card className="min-w-0 space-y-5 break-words p-4 md:p-5">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0"><h3 className="font-semibold text-slate-100">{t('longTerm.details', { name: item.name })}</h3>
        <p className="mt-1 text-xs text-slate-400">{t('longTerm.session')}: {item.asOf ?? '—'}</p></div>
      <button type="button" onClick={close} className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300">{t('longTerm.close')}</button>
    </div>
    <div role="tablist" aria-label={t('longTerm.tabs.label')} className="grid grid-cols-3 gap-1 rounded-lg bg-slate-800/50 p-1">
      {tabs.map((tab) => <button key={tab} type="button" role="tab" id={`${id}-tab-${tab}`} aria-controls={`${id}-panel-${tab}`} aria-selected={activeTab === tab} tabIndex={activeTab === tab ? 0 : -1}
        ref={(element) => { tabRefs.current[tab] = element }} onClick={() => selectTab(tab)} onKeyDown={(event) => navigateTabs(event, tab)}
        className={`min-w-0 rounded-md px-2 py-2 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 sm:text-sm ${activeTab === tab ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200'}`}>
        {t(`longTerm.tabs.${tab}`)}
      </button>)}
    </div>
    <div role="tabpanel" id={`${id}-panel-${activeTab}`} aria-labelledby={`${id}-tab-${activeTab}`} tabIndex={0} className="min-w-0 space-y-4 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400">
    {activeTab === 'overview' && <>
      <div className="grid gap-4 sm:grid-cols-3">
        {(['qualityScore', 'valueScore', 'momentumScore'] as const).map((key) => <div key={key} className="min-w-0 space-y-1 text-xs">
          <p className="text-slate-400">{t(`longTerm.${key}`)}</p>
          <LongTermFactorBar value={item[key]} label={t(`longTerm.${key}`)} />
        </div>)}
      </div>
      <LongTermInputs item={item} />
    </>}
    {activeTab !== 'overview' && <p className="rounded-lg bg-slate-800/50 p-3 text-xs leading-relaxed text-slate-400">{t('longTerm.historyExplanation')}</p>}
    {activeTab === 'scores' && <section aria-label={t('longTerm.scoreHistory')} className="space-y-3">
      <h4 className="text-sm font-semibold text-slate-200">{t('longTerm.scoreHistory')}</h4>
      {scores.loading && <p role="status" className="text-sm text-slate-400">{t('common.loading')}</p>}
      {scores.error && <LoadError retry={scores.refetch} />}
      {scores.data && !scores.data.dbEnabled && <p className="text-sm text-amber-400">{t('longTerm.storageUnavailable')}</p>}
      {scores.data?.dbEnabled && scores.data.items.length === 0 && <p className="text-sm text-slate-400">{t('longTerm.noScoreHistory')}</p>}
      {scores.data?.dbEnabled && <LongTermHistoryChart items={scores.data.items} />}
      {scores.data?.items.map((entry, index) => <details key={`${entry.recordedAt}-${index}`} className="rounded-lg border border-slate-800 p-3">
        <summary className="cursor-pointer text-sm text-slate-200">
          {t('longTerm.recordedAt')}: <time dateTime={entry.recordedAt} title={entry.recordedAt}>{timestamp(entry.recordedAt, i18n.language)}</time> · {t('longTerm.score')}: {scoreText(entry.score, i18n.language)}
        </summary>
        <div className="mt-3 space-y-3">
          <p className="text-xs text-slate-400">{t('longTerm.session')}: {entry.asOf ?? '—'} · {t('longTerm.modelVersion')}: {entry.modelVersion}</p>
          <p className="text-xs text-slate-200">{(['qualityScore', 'valueScore', 'momentumScore'] as const).map((key) => `${t(`longTerm.${key}`)}: ${scoreText(entry[key], i18n.language)}`).join(' · ')}</p>
          <p className="text-xs text-slate-400">{t('longTerm.coverage')}: {scoreText(entry.coverage, i18n.language)}%</p>
          <LongTermInputs item={entry} />
        </div>
      </details>)}
      {!!scores.data?.items.length && <p className="text-xs text-slate-500">{t('longTerm.latestScores')}</p>}
    </section>}
    {activeTab === 'financials' && <section aria-label={t('longTerm.financialHistory')} className="space-y-3">
      <h4 className="text-sm font-semibold text-slate-200">{t('longTerm.financialHistory')}</h4>
      {financials.loading && <p role="status" className="text-sm text-slate-400">{t('common.loading')}</p>}
      {financials.error && <LoadError retry={financials.refetch} />}
      {financials.data && !financials.data.dbEnabled && <p className="text-sm text-amber-400">{t('longTerm.storageUnavailable')}</p>}
      {financials.data?.dbEnabled && financials.data.items.length === 0 && <p className="text-sm text-slate-400">{t('longTerm.noFinancialHistory')}</p>}
      {financials.data?.items.map((entry, index) => <details key={`${entry.kind}-${entry.observedAt}-${index}`} className="rounded-lg border border-slate-800 p-3">
        <summary className="cursor-pointer text-sm text-slate-200">{t(`longTerm.kinds.${entry.kind}`)} · {t('longTerm.observedAt')}: <time dateTime={entry.observedAt} title={entry.observedAt}>{timestamp(entry.observedAt, i18n.language)}</time></summary>
        <div className="mt-3 space-y-3"><p className="text-xs text-slate-400">{t('longTerm.source')}: {entry.source}</p><FinancialPayload observation={entry} /></div>
      </details>)}
      {!!financials.data?.items.length && <p className="text-xs text-slate-500">{t('longTerm.latestFinancials')}</p>}
    </section>}
    </div>
    {tabs.filter((tab) => tab !== activeTab).map((tab) => <div key={tab} role="tabpanel" id={`${id}-panel-${tab}`} aria-labelledby={`${id}-tab-${tab}`} hidden />)}
  </Card>
}
