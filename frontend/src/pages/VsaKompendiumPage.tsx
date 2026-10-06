// VSA Kompendium — the full Volume Spread Analysis compendium as a public
// page, added 2026-09-25 at the owner's request ("I want to see
// kompendium_VSA.html on my website"), and since 2026-09-26 the first
// article of the Education section (/education/vsa-kompendium; the old
// /vsa-kompendium address redirects here).
//
// The article (frontend/src/content/vsaKompendium.md) is the owner's own
// compendium of Rafal Glinicki's VSA course, synthesised from the
// transcripts of all 34 recordings plus its implementation appendix — the
// same source that became the `vsa4` trading method (see
// backend-python/app/analysis/methods/vsa4.py and agent/vsa4-source/).
// Since 2026-09-26 it is in Polish AND English, by the owner's decision:
// the English translation is vsaKompendium.en.md, picked by the UI language,
// with English copies of the two diagrams (public/vsa/*.en.svg). The PDF
// exists in Polish only, and the English page says so on the button.

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, Download, ExternalLink, Library } from 'lucide-react'
import { MarkdownArticle } from '../components/MarkdownArticle'
import { DisclaimerNote } from '../components/ui'
import { articleBySlug, educationLanguage } from '../content/education'

const SOURCE_URL = 'https://www.xtb.com/pl/edukacja/investing-masters'

const article = articleBySlug('vsa-kompendium')!

export function VsaKompendiumPage() {
  const { t, i18n } = useTranslation()
  const lang = educationLanguage(i18n.resolvedLanguage ?? i18n.language)
  const diagramSuffix = lang === 'en' ? '.en' : ''

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-5xl">
      <Link
        to="/education"
        className="inline-flex w-fit items-center gap-1 text-xs font-medium text-slate-400 hover:text-emerald-400"
      >
        <ChevronLeft size={14} />
        {t('education.backToEducation')}
      </Link>

      {/* Header */}
      <div className="flex items-start gap-3 border-b border-slate-800 pb-6">
        <Library size={28} className="mt-0.5 shrink-0 text-emerald-500" />
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            {t('vsaKompendium.title')}
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {t('vsaKompendium.subtitle')}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            {t('vsaKompendium.languageNote')}
          </p>
        </div>
      </div>

      {/* Source + actions */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-xs text-slate-400">
        <span>
          {t('vsaKompendium.sourceLabel')}{' '}
          <a
            href={SOURCE_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-400 underline underline-offset-2 hover:text-emerald-300"
          >
            Rafał Glinicki — Analiza ceny i wolumenu (XTB Investing Masters)
            <ExternalLink size={11} className="ml-1 inline-block align-baseline" />
          </a>
        </span>
        <a
          href="/vsa/kompendium-vsa.pdf"
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800/60 px-3 py-1.5 font-medium text-slate-200 hover:bg-slate-800"
        >
          <Download size={13} />
          {t('vsaKompendium.downloadPdf')}
        </a>
      </div>

      {/* Reference diagrams, collapsed by default — same two schematics
          kompendium_VSA.html ships, own educational illustrations. */}
      <details className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium text-emerald-400">
          {t('vsaKompendium.diagramsToggle')}
        </summary>
        <div className="mt-4 space-y-4">
          <img
            src={`/vsa/anatomia${diagramSuffix}.svg`}
            alt={t('vsaKompendium.diagramAnatomyAlt')}
            className="w-full rounded-md border border-slate-800 bg-white"
          />
          <img
            src={`/vsa/wfo${diagramSuffix}.svg`}
            alt={t('vsaKompendium.diagramWfoAlt')}
            className="w-full rounded-md border border-slate-800 bg-white"
          />
          <p className="text-xs text-slate-500">{t('vsaKompendium.diagramsNote')}</p>
        </div>
      </details>

      <DisclaimerNote />

      <MarkdownArticle
        markdown={article.content[lang]}
        tocHeading={t('vsaKompendium.tocHeading')}
      />
    </div>
  )
}
