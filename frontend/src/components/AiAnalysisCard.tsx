// AI Insight card (stock detail page) — the built-in analysis engine's
// second opinion on the rule-detected VSA signals. Computed locally by the
// backend (app/analysis/ai_insight.py); no external AI services involved.

import { useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, Sparkles } from 'lucide-react'
import { Card, CardTitle, InfoTip } from './ui'
import { useAiAnalysis } from '../hooks/useAiAnalysis'
import type { ApiAiSignalAssessment } from '../api/stocksApi'
import type { SignalVerdict } from '../types'

/** Badge styling per verdict — emerald for strength, rose for weakness. */
const VERDICT_BADGE: Record<SignalVerdict, string> = {
  'Strong Buy': 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
  Buy: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/20',
  Hold: 'bg-slate-500/15 text-slate-300 ring-slate-500/30',
  Sell: 'bg-rose-500/10 text-rose-300 ring-rose-500/20',
  'Strong Sell': 'bg-rose-500/15 text-rose-400 ring-rose-500/30',
}

const AGREEMENT_STYLE: Record<
  ApiAiSignalAssessment['agreement'],
  { icon: string; cls: string; label: string }
> = {
  confirm: { icon: '✓', cls: 'bg-emerald-500/20 text-emerald-400', label: 'Confirmed' },
  reject: { icon: '✕', cls: 'bg-rose-500/15 text-rose-400', label: 'Rejected' },
  uncertain: { icon: '?', cls: 'bg-amber-500/15 text-amber-400', label: 'Uncertain' },
}

function AssessmentRow({ a }: { a: ApiAiSignalAssessment }) {
  const style = AGREEMENT_STYLE[a.agreement]
  return (
    <li className="py-2">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          <span
            className={
              'grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold ' +
              style.cls
            }
            title={style.label}
          >
            {style.icon}
          </span>
          <span className="text-slate-200">{a.signalName}</span>
        </span>
        <span className="text-xs tabular-nums text-slate-500">{a.date}</span>
      </div>
      <p className="mt-1 pl-6 text-xs leading-relaxed text-slate-400">{a.comment}</p>
    </li>
  )
}

export function AiAnalysisCard({ ticker }: { ticker: string }) {
  const { data, loading, error } = useAiAnalysis(ticker)
  const [showSignals, setShowSignals] = useState(false)

  return (
    <Card>
      <CardTitle>
        <span className="inline-flex items-center gap-1.5">
          <Sparkles size={14} className="text-emerald-400" /> AI Insight
        </span>{' '}
        <InfoTip text="A second opinion from StockPilot's built-in analysis engine. It judges each detected VSA signal by what price and volume actually did afterwards (follow-through), the trend it fired in, and how often that signal worked on this stock historically — then combines everything into a verdict. Computed locally on the server; deterministic and free." />
      </CardTitle>

      <div className="px-4 pb-4">
        {loading && !data && (
          <div className="flex items-center gap-2 py-2 text-sm text-slate-500">
            <Loader2 size={14} className="animate-spin" /> Analysing…
          </div>
        )}

        {error && !data && (
          <p className="py-2 text-xs text-slate-500">
            AI insight unavailable: {error}
          </p>
        )}

        {data && (
          <>
            <div className="flex items-center gap-3">
              <span
                className={
                  'rounded-md px-2.5 py-1 text-sm font-semibold ring-1 ring-inset ' +
                  VERDICT_BADGE[data.verdict]
                }
              >
                {data.verdict}
              </span>
              <div className="flex-1">
                <div className="mb-1 flex justify-between text-xs text-slate-500">
                  <span>Confidence</span>
                  <span className="tabular-nums text-slate-300">
                    {data.confidence}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-800">
                  <div
                    className="h-1.5 rounded-full bg-emerald-500/70"
                    style={{ width: `${data.confidence}%` }}
                  />
                </div>
              </div>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-slate-400">
              {data.summary}
            </p>

            {data.keyObservations.length > 0 && (
              <ul className="mt-3 space-y-1.5 border-t border-slate-800 pt-3">
                {data.keyObservations.map((obs) => (
                  <li key={obs} className="flex gap-2 text-xs text-slate-400">
                    <span className="text-emerald-500/70">•</span>
                    <span>{obs}</span>
                  </li>
                ))}
              </ul>
            )}

            {data.signalAssessments.length > 0 && (
              <div className="mt-3 border-t border-slate-800 pt-2">
                <button
                  onClick={() => setShowSignals((s) => !s)}
                  className="flex w-full items-center justify-between py-1 text-xs font-medium text-slate-300 hover:text-slate-100"
                  aria-expanded={showSignals}
                >
                  Signal-by-signal review ({data.signalAssessments.length})
                  {showSignals ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showSignals && (
                  <ul className="divide-y divide-slate-800/60">
                    {data.signalAssessments.map((a) => (
                      <AssessmentRow key={a.signalName + a.date} a={a} />
                    ))}
                  </ul>
                )}
              </div>
            )}

            <p className="mt-3 text-[10px] text-slate-600">
              {data.engine} · as of {data.asOf} · analysis of historical data, not
              investment advice
            </p>
          </>
        )}
      </div>
    </Card>
  )
}
