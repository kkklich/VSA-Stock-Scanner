export function scoreText(value: number | null, locale: string): string {
  return value === null ? '—' : value.toLocaleString(locale, { maximumFractionDigits: 1 })
}
