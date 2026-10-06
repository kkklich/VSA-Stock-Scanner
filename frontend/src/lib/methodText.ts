// A trading method's description in the visitor's language.
//
// The catalogue (GET /api/stocks/methods) carries each method's description in
// English, written next to the method's code, and that stays the single
// source. The Polish translations live in pl.json under
// `methodDescriptions.<method id>` (added 2026-09-26 with the Education
// section, whose every text is PL + EN). A method without a translation —
// a newly added one — falls back to the backend's English, so it never shows
// a blank or a raw key.
//
// backend-python/tests/test_education_sync.py fails when a registered method
// has no Polish description, or when a method's English description changes
// without its Polish one being reviewed.

import type { TFunction } from 'i18next'

export function methodDescription(
  t: TFunction,
  method: { id: string; description: string },
): string {
  return t(`methodDescriptions.${method.id}`, { defaultValue: method.description })
}
