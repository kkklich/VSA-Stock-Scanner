// Every Education article is published in Polish AND English (owner's
// decision, 2026-09-26). These tests guard that a translation never goes
// missing or drifts structurally from its original — a dropped section or
// table in one language would be easy to miss by eye in a 580-line article.

import { describe, expect, it } from 'vitest'
import {
  EDUCATION_ARTICLES,
  articleBySlug,
  articlesForMethod,
  educationLanguage,
} from './education'
import en from '../i18n/locales/en.json'
import pl from '../i18n/locales/pl.json'

/** Counts of each heading level and of tables — the article's skeleton. */
function skeleton(md: string) {
  const lines = md.split('\n')
  const count = (re: RegExp) => lines.filter((l) => re.test(l)).length
  return {
    h1: count(/^# /),
    h2: count(/^## /),
    h3: count(/^### /),
    h4: count(/^#### /),
    tables: count(/^\|---/),
    fences: count(/^```/),
  }
}

type ArticleStrings = Record<string, { title: string; summary: string }>

describe('Education articles', () => {
  it.each(EDUCATION_ARTICLES.map((a) => [a.slug, a] as const))(
    '%s exists in both languages with the same structure',
    (_slug, article) => {
      expect(article.content.pl.length).toBeGreaterThan(1000)
      expect(article.content.en.length).toBeGreaterThan(1000)
      expect(article.content.en).not.toBe(article.content.pl)
      expect(skeleton(article.content.en)).toEqual(skeleton(article.content.pl))
    },
  )

  it.each(EDUCATION_ARTICLES.map((a) => [a.slug, a.i18nKey] as const))(
    '%s has a title and summary in both UI languages',
    (_slug, key) => {
      for (const locale of [en, pl]) {
        const entry = (locale.education.articles as ArticleStrings)[key]
        expect(entry.title).toBeTruthy()
        expect(entry.summary).toBeTruthy()
      }
    },
  )

  it('links between articles only to articles that exist', () => {
    for (const article of EDUCATION_ARTICLES) {
      for (const md of [article.content.pl, article.content.en]) {
        for (const [, slug] of md.matchAll(/\]\(\/education\/([a-z0-9-]+)\)/g)) {
          expect(articleBySlug(slug), `${article.slug} links /education/${slug}`).toBeDefined()
        }
      }
    }
  })

  it('uses unique slugs', () => {
    const slugs = EDUCATION_ARTICLES.map((a) => a.slug)
    expect(new Set(slugs).size).toBe(slugs.length)
  })

  it('finds articles by slug and by the method they explain', () => {
    expect(articleBySlug('vsa-kompendium')?.slug).toBe('vsa-kompendium')
    expect(articleBySlug('nope')).toBeUndefined()
    expect(articlesForMethod('vsa4').map((a) => a.slug)).toEqual(['vsa-kompendium'])
    // The VSA rating has its own article first, then the deeper compendium.
    expect(articlesForMethod('vsa').map((a) => a.slug)).toEqual(['vsa-rating', 'vsa-kompendium'])
    expect(articlesForMethod('minervini').map((a) => a.slug)).toEqual(['minervini'])
    expect(articlesForMethod('breakout').map((a) => a.slug)).toEqual(['volume-breakout'])
    expect(articlesForMethod('weinstein').map((a) => a.slug)).toEqual(['weinstein'])
    expect(articlesForMethod('pocket_pivot').map((a) => a.slug)).toEqual(['pocket-pivot'])
    expect(articlesForMethod('no-such-method')).toEqual([])
  })

  it('reads Polish for any Polish tag and English otherwise', () => {
    expect(educationLanguage('pl')).toBe('pl')
    expect(educationLanguage('pl-PL')).toBe('pl')
    expect(educationLanguage('en-US')).toBe('en')
    expect(educationLanguage('de')).toBe('en')
    expect(educationLanguage(undefined)).toBe('en')
  })
})
