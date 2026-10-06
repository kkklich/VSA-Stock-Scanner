import { describe, expect, it } from 'vitest'
import { extractToc } from './markdownToc'

describe('extractToc', () => {
  it('lists # and ## headings with rehype-slug compatible ids', () => {
    const toc = extractToc('# Title\n\n## 1. What VSA is\n\n### Detail\n\n## 1. What VSA is\n')
    expect(toc).toEqual([
      { id: 'title', title: 'Title' },
      { id: '1-what-vsa-is', title: '1. What VSA is' },
      // The repeated title gets the same "-1" suffix rehype-slug gives it.
      { id: '1-what-vsa-is-1', title: '1. What VSA is' },
    ])
  })

  it('ignores lines inside fenced code blocks', () => {
    const toc = extractToc('## Real\n\n```text\n# not a heading\n```\n\n## After\n')
    expect(toc.map((e) => e.title)).toEqual(['Real', 'After'])
  })
})
