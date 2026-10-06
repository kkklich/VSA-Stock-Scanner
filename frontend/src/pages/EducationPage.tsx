// Education — the landing page of the section that holds the knowledge behind
// every trading method in the app (agent/ROADMAP.md #32, owner-requested
// 2026-09-26). Two lists:
//
//  1. Articles — one per trading method plus the long VSA Kompendium, from
//     the registry in content/education.ts, each in Polish and English.
//  2. Trading methods — one card per method the app ranks by, read from the
//     live catalogue (GET /api/stocks/methods), so a newly registered method
//     appears here by itself. A card links every article that explains its
//     method, or says one is still to be written.

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowRight,
  BookOpenText,
  ExternalLink,
  GraduationCap,
  Library,
} from 'lucide-react'
import { useMethods } from '../hooks/useMethods'
import { EDUCATION_ARTICLES, articlesForMethod } from '../content/education'
import { DisclaimerNote } from '../components/ui'
import { methodDescription } from '../lib/methodText'

export function EducationPage() {
  const { t } = useTranslation()
  const { methods, loading, error } = useMethods()

  return (
    <div className="flex flex-col gap-8 p-4 sm:p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-start gap-3 border-b border-slate-800 pb-6">
        <GraduationCap size={28} className="mt-0.5 shrink-0 text-emerald-500" />
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{t('education.title')}</h1>
          <p className="mt-1 text-sm text-slate-400">{t('education.subtitle')}</p>
        </div>
      </div>

      {/* Articles */}
      <section aria-labelledby="education-articles">
        <h2
          id="education-articles"
          className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          {t('education.articlesHeading')}
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {EDUCATION_ARTICLES.map((a) => (
            <Link
              key={a.slug}
              to={`/education/${a.slug}`}
              className="group flex flex-col gap-2 rounded-xl border border-slate-800 bg-slate-900 p-5 transition-colors hover:border-emerald-500/50"
            >
              <div className="flex items-center gap-2">
                {a.slug === 'vsa-kompendium' ? (
                  <Library size={18} className="shrink-0 text-emerald-500" />
                ) : (
                  <BookOpenText size={18} className="shrink-0 text-emerald-500" />
                )}
                <h3 className="text-base font-semibold text-slate-100">
                  {t(`education.articles.${a.i18nKey}.title`)}
                </h3>
              </div>
              <p className="text-sm leading-relaxed text-slate-400">
                {t(`education.articles.${a.i18nKey}.summary`)}
              </p>
              <div className="mt-auto flex items-center justify-between pt-2 text-xs">
                <span className="rounded border border-slate-700 px-1.5 py-0.5 font-medium text-slate-400">
                  PL · EN
                </span>
                <span className="inline-flex items-center gap-1 font-medium text-emerald-400 group-hover:text-emerald-300">
                  {t('education.read')}
                  <ArrowRight size={13} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Trading methods */}
      <section aria-labelledby="education-methods">
        <h2
          id="education-methods"
          className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          {t('education.methodsHeading')}
        </h2>
        <p className="mb-3 text-sm text-slate-400">{t('education.methodsIntro')}</p>

        {loading && (
          <p className="text-sm text-slate-500">{t('education.methodsLoading')}</p>
        )}
        {!loading && error && (
          <p className="text-sm text-slate-500">{t('education.methodsError')}</p>
        )}

        {!loading && !error && (
          <ul className="grid gap-4 md:grid-cols-2">
            {methods.map((m) => {
              const articles = articlesForMethod(m.id)
              return (
                <li
                  key={m.id}
                  className="flex flex-col gap-2 rounded-xl border border-slate-800 bg-slate-900 p-5"
                >
                  <h3 className="text-base font-semibold text-slate-100">{m.name}</h3>
                  <p className="text-sm leading-relaxed text-slate-400">{methodDescription(t, m)}</p>
                  {m.source && (
                    <p className="text-xs text-slate-500">
                      {t('education.source')}{' '}
                      {m.sourceUrl ? (
                        <a
                          href={m.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-slate-400 underline underline-offset-2 hover:text-emerald-400"
                        >
                          {m.source}
                          <ExternalLink size={10} className="ml-1 inline-block align-baseline" />
                        </a>
                      ) : (
                        <span className="text-slate-400">{m.source}</span>
                      )}
                    </p>
                  )}
                  <div className="mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-2 text-xs">
                    {articles.length > 0 ? (
                      articles.map((article) => (
                        <Link
                          key={article.slug}
                          to={`/education/${article.slug}`}
                          className="inline-flex items-center gap-1 font-medium text-emerald-400 hover:text-emerald-300"
                        >
                          <BookOpenText size={13} />
                          {t(`education.articles.${article.i18nKey}.title`)}
                          <ArrowRight size={13} />
                        </Link>
                      ))
                    ) : (
                      <span className="text-slate-500">{t('education.articleComingSoon')}</span>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <DisclaimerNote />
    </div>
  )
}
