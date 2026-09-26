// VSA Kompendium — the full Volume Spread Analysis compendium as a public
// page, added 2026-09-25 at the owner's request ("I want to see
// kompendium_VSA.html on my website").
//
// The article itself (frontend/src/content/vsaKompendium.md) is the owner's
// own compendium of Rafal Glinicki's VSA course, synthesised from the
// transcripts of all 34 recordings plus its implementation appendix — the
// same source that became the `vsa4` trading method (see
// backend-python/app/analysis/methods/vsa4.py and agent/vsa4-source/).
// It stays in its source language (Polish) even when the UI is switched to
// English, like a reference document rather than app chrome — only the page
// furniture (title, notes, buttons) is translated. Rendered from raw
// Markdown with react-markdown + remark-gfm (tables) + rehype-slug (heading
// anchors), so the content file can be updated without touching this
// component.
//
// The two reference diagrams and the source PDF are static files copied
// alongside the docs (frontend/public/vsa/), served as-is.

import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'
import type { Components } from 'react-markdown'
import { Download, ExternalLink, Library, ListTree } from 'lucide-react'
import vsaKompendiumMd from '../content/vsaKompendium.md?raw'
import { extractVsaToc } from '../lib/vsaKompendiumToc'
import { DisclaimerNote } from '../components/ui'

const toc = extractVsaToc(vsaKompendiumMd)

const SOURCE_URL = 'https://www.xtb.com/pl/edukacja/investing-masters'

/** Tailwind classes for the rendered Markdown, matching the app's dark/light
 *  semantic neutral ramp (see CLAUDE.md "Conventions"). */
const markdownComponents: Components = {
  h1: ({ children, id }) => (
    <h1
      id={id}
      className="scroll-mt-20 text-2xl font-bold text-slate-100 mt-2 mb-4"
    >
      {children}
    </h1>
  ),
  h2: ({ children, id }) => (
    <h2
      id={id}
      className="scroll-mt-20 border-t border-slate-800 pt-6 mt-10 text-xl font-bold text-slate-100"
    >
      {children}
    </h2>
  ),
  h3: ({ children, id }) => (
    <h3 id={id} className="scroll-mt-20 mt-7 text-base font-semibold text-slate-100">
      {children}
    </h3>
  ),
  h4: ({ children, id }) => (
    <h4 id={id} className="scroll-mt-20 mt-5 text-sm font-semibold text-slate-200">
      {children}
    </h4>
  ),
  p: ({ children }) => (
    <p className="my-3 text-sm leading-relaxed text-slate-300">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-300">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-3 list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-slate-300">
      {children}
    </ol>
  ),
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-100">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ children, href = '' }) => (
    <a
      href={href}
      target={href.startsWith('http') ? '_blank' : undefined}
      rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
      className="text-emerald-400 underline underline-offset-2 hover:text-emerald-300"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-8 border-slate-800" />,
  code: ({ children }) => (
    <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs font-mono text-emerald-300">
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-900/60">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-slate-800 px-3 py-2 text-left align-top font-semibold text-slate-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-slate-800 px-3 py-2 align-top text-slate-300">
      {children}
    </td>
  ),
}

/** The list of section links, shared by the mobile collapsible ToC and the
 *  desktop sticky sidebar so the two never drift apart. */
function TocList({ className = '' }: { className?: string }) {
  return (
    <ul className={'space-y-1 text-sm ' + className}>
      {toc.map(({ id, title }) => (
        <li key={id}>
          <a
            href={`#${id}`}
            className="block rounded px-1.5 py-1 leading-snug text-slate-400 hover:bg-slate-800/60 hover:text-emerald-400"
          >
            {title}
          </a>
        </li>
      ))}
    </ul>
  )
}

export function VsaKompendiumPage() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-5xl">
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
            src="/vsa/anatomia.svg"
            alt={t('vsaKompendium.diagramAnatomyAlt')}
            className="w-full rounded-md border border-slate-800 bg-white"
          />
          <img
            src="/vsa/wfo.svg"
            alt={t('vsaKompendium.diagramWfoAlt')}
            className="w-full rounded-md border border-slate-800 bg-white"
          />
          <p className="text-xs text-slate-500">{t('vsaKompendium.diagramsNote')}</p>
        </div>
      </details>

      <DisclaimerNote />

      {/* Mobile / tablet: a collapsible table of contents ahead of the
          article, so a reader can jump to a section without first scrolling
          past the whole ~500-line compendium to find the sticky sidebar
          version below (which only appears from `lg` up). */}
      <details className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 lg:hidden">
        <summary className="cursor-pointer text-sm font-medium text-emerald-400">
          {t('vsaKompendium.tocHeading')}
        </summary>
        <TocList className="mt-3" />
      </details>

      <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
        {/* Table of contents — desktop sticky sidebar */}
        <nav
          aria-label={t('vsaKompendium.tocHeading')}
          className="hidden shrink-0 rounded-lg border border-slate-800 bg-slate-900/40 p-4 lg:sticky lg:top-4 lg:block lg:w-64"
        >
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <ListTree size={13} />
            {t('vsaKompendium.tocHeading')}
          </div>
          <TocList />
        </nav>

        {/* Article */}
        <article className="min-w-0 flex-1">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSlug]}
            components={markdownComponents}
          >
            {vsaKompendiumMd}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  )
}
