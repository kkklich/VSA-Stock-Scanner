// The Education section's article registry (agent/ROADMAP.md #32, started
// 2026-09-26): the owner asked for one place on the site that holds the
// knowledge behind every trading method in the app, with the VSA Kompendium
// as its first article, and for every article in Polish AND English.
//
// Adding an article is: write `<name>.md` (Polish) and `<name>.en.md`
// (English) in this folder, add an entry below, and list the trading-method
// ids it explains in `methodIds`. The Education landing page then links it
// from the article list and from those methods' cards, and it is served at
// /education/<slug> by the generic article page. A method no article covers
// yet still gets a card (the catalogue comes from GET /api/stocks/methods)
// marked "article coming soon".
//
// The method articles describe the rules exactly as the code in
// backend-python/app/analysis/methods/ checks them, and quote the measured
// results (agent/CODEBASE-OVERVIEW.md §3.3a, agent/SIGNAL-DIRECTION-TEST.md).
// If a method's rules or its measurements change, update its article in BOTH
// languages.

import vsaKompendiumPl from './vsaKompendium.md?raw'
import vsaKompendiumEn from './vsaKompendium.en.md?raw'
import vsaRatingPl from './vsaRating.md?raw'
import vsaRatingEn from './vsaRating.en.md?raw'
import minerviniPl from './minervini.md?raw'
import minerviniEn from './minervini.en.md?raw'
import volumeBreakoutPl from './volumeBreakout.md?raw'
import volumeBreakoutEn from './volumeBreakout.en.md?raw'
import weinsteinPl from './weinstein.md?raw'
import weinsteinEn from './weinstein.en.md?raw'
import pocketPivotPl from './pocketPivot.md?raw'
import pocketPivotEn from './pocketPivot.en.md?raw'

export type EducationLanguage = 'pl' | 'en'

export interface EducationArticle {
  /** URL segment: the article lives at /education/<slug>. */
  slug: string
  /** Key under `education.articles.<key>` in the translation files. */
  i18nKey: string
  /** Trading-method ids (as in GET /api/stocks/methods) this article explains. */
  methodIds: string[]
  /** The article itself, one Markdown document per language. */
  content: Record<EducationLanguage, string>
}

/** In display order: the method articles first, the long compendium last. */
export const EDUCATION_ARTICLES: EducationArticle[] = [
  {
    slug: 'vsa-rating',
    i18nKey: 'vsaRating',
    methodIds: ['vsa'],
    content: { pl: vsaRatingPl, en: vsaRatingEn },
  },
  {
    slug: 'minervini',
    i18nKey: 'minervini',
    methodIds: ['minervini'],
    content: { pl: minerviniPl, en: minerviniEn },
  },
  {
    slug: 'volume-breakout',
    i18nKey: 'volumeBreakout',
    methodIds: ['breakout'],
    content: { pl: volumeBreakoutPl, en: volumeBreakoutEn },
  },
  {
    slug: 'weinstein',
    i18nKey: 'weinstein',
    methodIds: ['weinstein'],
    content: { pl: weinsteinPl, en: weinsteinEn },
  },
  {
    slug: 'pocket-pivot',
    i18nKey: 'pocketPivot',
    methodIds: ['pocket_pivot'],
    content: { pl: pocketPivotPl, en: pocketPivotEn },
  },
  {
    slug: 'vsa-kompendium',
    i18nKey: 'vsaKompendium',
    // The compendium is the source of the three Glinicki-course methods and
    // the deeper reading behind the app's VSA rating.
    methodIds: ['vsa', 'glinicki', 'vsa3', 'vsa4'],
    content: { pl: vsaKompendiumPl, en: vsaKompendiumEn },
  },
]

export function articleBySlug(slug: string): EducationArticle | undefined {
  return EDUCATION_ARTICLES.find((a) => a.slug === slug)
}

/** Every article that explains a trading method, most specific first. */
export function articlesForMethod(methodId: string): EducationArticle[] {
  return EDUCATION_ARTICLES.filter((a) => a.methodIds.includes(methodId))
}

/** The article language for a UI language tag ("pl", "pl-PL", "en-US" …):
 *  Polish for Polish, English for everything else. */
export function educationLanguage(uiLanguage: string | undefined): EducationLanguage {
  return (uiLanguage ?? '').toLowerCase().startsWith('pl') ? 'pl' : 'en'
}
