// Table-of-contents extraction for the Education articles (the VSA
// Kompendium and every article after it).
//
// Articles are rendered from raw Markdown by react-markdown, and
// `rehype-slug` assigns each heading (h1-h6, every level, in document order)
// an id via `github-slugger`. To link to those ids from a sidebar table of
// contents we need the SAME ids — so this walks the same document with our
// own `github-slugger` instance, in the same order, and keeps only the
// top-level (`#`/`##`) headings for the list a reader actually navigates by.
// Deeper headings (`###`/`####`, individual signals) still have to be
// slugged here even though they are not listed, purely so the slug counters
// (duplicate-title disambiguation) stay in lockstep with rehype-slug's.

import GithubSlugger from 'github-slugger'

export type TocEntry = {
  id: string
  title: string
}

const HEADING_LINE = /^(#{1,4})\s+(.*)$/

export function extractToc(markdown: string): TocEntry[] {
  const slugger = new GithubSlugger()
  const toc: TocEntry[] = []
  let inFence = false

  for (const line of markdown.split('\n')) {
    // A `#` inside a fenced code block is not a heading (rehype-slug never
    // sees it as one), so skip fenced blocks to keep the ids in step.
    if (line.startsWith('```')) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const match = HEADING_LINE.exec(line)
    if (!match) continue
    const level = match[1].length
    const title = match[2].trim()
    const id = slugger.slug(title)
    if (level <= 2) toc.push({ id, title })
  }

  return toc
}
