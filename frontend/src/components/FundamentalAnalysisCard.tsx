import { useTranslation } from 'react-i18next'
import type { FundamentalAssessment } from '../types/longTerm'
import { scoreText } from '../lib/longTerm'
import { LongTermFactorBar } from './LongTermFactorBar'

const MULTIPLES = new Set(['netDebtToEbitda', 'interestCoverage', 'cashConversion'])

export function FundamentalAnalysisCard({ analysis }: { analysis: FundamentalAssessment }) {
  const { t, i18n } = useTranslation()
  return <section aria-label={t('fundamentals.title')} className="space-y-4 rounded-lg border border-slate-700 p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h4 className="font-semibold text-slate-100">{t('fundamentals.title')}</h4>
        <p className="mt-1 text-xs text-slate-400">{t(`fundamentals.profiles.${analysis.profile}`)} · {analysis.modelVersion}</p>
      </div>
      <p className="text-xl font-semibold tabular-nums text-slate-100">{scoreText(analysis.score, i18n.language)} <span className="text-xs font-normal text-slate-400">/ 100</span></p>
    </div>
    <p className="text-xs leading-relaxed text-slate-400">{t('fundamentals.methodology')}</p>
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5">
      {Object.entries(analysis.pillars).map(([key, score]) => <div key={key} className="min-w-0 space-y-2 text-xs">
        <p className="text-slate-300">{t(`fundamentals.pillars.${key}`)}</p>
        <LongTermFactorBar value={score} label={t(`fundamentals.pillars.${key}`)} />
      </div>)}
    </div>
    <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-400">
      <div><dt>{t('fundamentals.coverage')}</dt><dd className="mt-1 text-slate-200">{scoreText(analysis.coverage, i18n.language)}%</dd></div>
      <div><dt>{t('fundamentals.latestPeriod')}</dt><dd className="mt-1 text-slate-200">{analysis.latestPeriodEnd ?? '—'}</dd></div>
      <div><dt>{t('fundamentals.annualPeriod')}</dt><dd className="mt-1 text-slate-200">{analysis.annualPeriodEnd ?? '—'}</dd></div>
    </dl>
    <p className="text-xs text-slate-400">{t('longTerm.comparison', { group: t(`longTerm.groups.${analysis.comparisonGroup}`), peers: analysis.peerCount })}</p>
    {analysis.notApplicable.length > 0 && <p className="text-xs leading-relaxed text-slate-400">{t('fundamentals.notApplicable', { pillars: analysis.notApplicable.map((key) => t(`fundamentals.pillars.${key}`)).join(', ') })}</p>}
    {analysis.missing.length > 0 && <p className="text-xs leading-relaxed text-amber-400">{analysis.missing.map((key) => t(`fundamentals.missing.${key}`, { defaultValue: t(`longTerm.missing.${key}`, { defaultValue: t('longTerm.missing.unknown') }) })).join(' · ')}</p>}
    {analysis.warnings.length > 0 && <ul className="space-y-1 text-xs leading-relaxed text-amber-400">{analysis.warnings.map((key) => <li key={key}>{t(`fundamentals.warnings.${key}`)}</li>)}</ul>}
    <details>
      <summary className="cursor-pointer text-xs font-medium text-slate-300">{t('fundamentals.showInputs')}</summary>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">
        {Object.entries(analysis.inputs).map(([key, value]) => <div key={key} className="min-w-0 text-xs">
          <p className="text-slate-400">{t(`fundamentals.inputs.${key}`)}</p>
          <p className="mt-1 tabular-nums text-slate-200">{value == null ? '—' : MULTIPLES.has(key) ? `${value.toLocaleString(i18n.language, { maximumFractionDigits: 2 })}×` : value.toLocaleString(i18n.language, { style: 'percent', maximumFractionDigits: 2 })}</p>
          {analysis.metricScores[key] != null && <p className="mt-1 text-slate-500">{t('fundamentals.metricScore', { score: scoreText(analysis.metricScores[key], i18n.language) })}</p>}
        </div>)}
      </div>
    </details>
  </section>
}
