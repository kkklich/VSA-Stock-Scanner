// One Education article (/education/<slug>) — the reader for every article
// in content/education.ts except the VSA Kompendium, which has its own page
// for its source link, PDF and diagrams. Added 2026-09-26 with the first
// method articles (agent/ROADMAP.md #32).
//
// The article follows the interface language (every article exists in Polish
// and English). An unknown slug goes back to the Education landing page.

import { Link, Navigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpenText, ChevronLeft } from 'lucide-react'
import { MarkdownArticle } from '../components/MarkdownArticle'
import { DisclaimerNote } from '../components/ui'
import { articleBySlug, educationLanguage } from '../content/education'

export function EducationArticlePage() {
  const { slug = '' } = useParams()
  const { t, i18n } = useTranslation()
  const article = articleBySlug(slug)

  if (!article) return <Navigate to="/education" replace />

  const lang = educationLanguage(i18n.resolvedLanguage ?? i18n.language)
  const key = `education.articles.${article.i18nKey}`

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-5xl">
      <Link
        to="/education"
        className="inline-flex w-fit items-center gap-1 text-xs font-medium text-slate-400 hover:text-emerald-400"
      >
        <ChevronLeft size={14} />
        {t('education.backToEducation')}
      </Link>

      <div className="flex items-start gap-3 border-b border-slate-800 pb-6">
        <BookOpenText size={28} className="mt-0.5 shrink-0 text-emerald-500" />
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{t(`${key}.title`)}</h1>
          <p className="mt-1 text-sm text-slate-400">{t(`${key}.summary`)}</p>
          <p className="mt-2 text-xs text-slate-500">{t('education.languageNote')}</p>
        </div>
      </div>

      <DisclaimerNote />

      <MarkdownArticle markdown={article.content[lang]} tocHeading={t('education.tocHeading')} />
    </div>
  )
}
