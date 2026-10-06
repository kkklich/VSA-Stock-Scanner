import { afterEach, describe, expect, it } from 'vitest'
import i18n from '../i18n'
import { methodDescription } from './methodText'

const MINERVINI = { id: 'minervini', description: 'English text from the backend.' }
const UNKNOWN = { id: 'not_translated_yet', description: 'Only in English so far.' }

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('methodDescription', () => {
  it('keeps the backend English in English', async () => {
    await i18n.changeLanguage('en')
    expect(methodDescription(i18n.t, MINERVINI)).toBe('English text from the backend.')
  })

  it('shows the Polish translation in Polish', async () => {
    await i18n.changeLanguage('pl')
    expect(methodDescription(i18n.t, MINERVINI)).toMatch(/^Mechaniczny filtr Marka Minerviniego/)
  })

  it('falls back to the English for a method with no translation yet', async () => {
    await i18n.changeLanguage('pl')
    expect(methodDescription(i18n.t, UNKNOWN)).toBe('Only in English so far.')
  })
})
