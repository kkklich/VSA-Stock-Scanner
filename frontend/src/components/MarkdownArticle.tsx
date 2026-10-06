// The reader every Education article shares: a Markdown document rendered
// with react-markdown + remark-gfm (tables) + rehype-slug (heading anchors),
// with a table of contents — collapsible above the article on phones and
// tablets, a sticky sidebar from `lg` up.
//
// Extracted from the VSA Kompendium page (2026-09-26) when the Education
// section was started, so every later article (one per trading method, see
// agent/ROADMAP.md #32) reads exactly the same way: the content is a
// Markdown file, the page around it only adds its own header.

import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'
import type { Components } from 'react-markdown'
import { ListTree } from 'lucide-react'
import { extractToc, type TocEntry } from '../lib/markdownToc'

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
  // A link to another page of the app ("/education/weinstein") goes through
  // the router, so moving between articles does not reload the whole site.
  a: ({ children, href = '' }) =>
    href.startsWith('/') ? (
      <Link
        to={href}
        className="text-emerald-400 underline underline-offset-2 hover:text-emerald-300"
      >
        {children}
      </Link>
    ) : (
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
  // Fenced blocks (```text …```) scroll sideways inside their own box, so a
  // long command line never widens the page on a phone.
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900 px-3 py-2.5 text-xs leading-relaxed">
      {children}
    </pre>
  ),
  code: ({ children, className }) =>
    className?.startsWith('language-') ? (
      <code className="font-mono text-emerald-300">{children}</code>
    ) : (
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
function TocList({ toc, className = '' }: { toc: TocEntry[]; className?: string }) {
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

export function MarkdownArticle({
  markdown,
  tocHeading,
}: {
  markdown: string
  /** Label of the table of contents, already translated. */
  tocHeading: string
}) {
  const toc = useMemo(() => extractToc(markdown), [markdown])

  return (
    <>
      {/* Mobile / tablet: a collapsible table of contents ahead of the
          article, so a reader can jump to a section without first scrolling
          past the whole article to find the sticky sidebar version below
          (which only appears from `lg` up). */}
      <details className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 lg:hidden">
        <summary className="cursor-pointer text-sm font-medium text-emerald-400">
          {tocHeading}
        </summary>
        <TocList toc={toc} className="mt-3" />
      </details>

      <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
        {/* Table of contents — desktop sticky sidebar */}
        <nav
          aria-label={tocHeading}
          className="hidden shrink-0 rounded-lg border border-slate-800 bg-slate-900/40 p-4 lg:sticky lg:top-4 lg:block lg:w-64"
        >
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <ListTree size={13} />
            {tocHeading}
          </div>
          <TocList toc={toc} />
        </nav>

        {/* Article */}
        <article className="min-w-0 flex-1">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSlug]}
            components={markdownComponents}
          >
            {markdown}
          </ReactMarkdown>
        </article>
      </div>
    </>
  )
}
