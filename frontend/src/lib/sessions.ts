// "Are all these rows from the same session?" — the question only a pooled
// ("All markets") list has to ask itself.
//
// Exchanges settle hours apart: the European ones in the late Warsaw afternoon
// (the GPW at 17:20, Xetra/Euronext/London around 17:55), the US only at ~22:15
// Warsaw time, after which the US ingest runs at 23:15. So for several hours
// every weekday evening a pooled list legitimately carries today's European
// rows beside yesterday's American ones — and the Dashboard opens on "biggest
// movers", which then silently compares today's moves to yesterday's.
//
// Nothing is wrong with the data; the US session simply has not happened yet.
// What was wrong was that the list could not say so. Each row now carries the
// session it describes (`lastSession`), and these read it back.

export interface SessionRow {
  lastSession?: string | null
}

/** The distinct sessions among the rows, newest first. */
export function sessionsOf(rows: readonly SessionRow[]): string[] {
  const seen = new Set<string>()
  for (const r of rows) if (r.lastSession) seen.add(r.lastSession)
  // ISO dates sort lexicographically the same way they sort chronologically.
  return [...seen].sort().reverse()
}

/**
 * How many of the rows are behind the newest session present, and which
 * sessions are involved. `null` when the rows agree — or when none of them say,
 * which is what an older backend's payload looks like.
 */
export function sessionMismatch(rows: readonly SessionRow[]): {
  newest: string
  oldest: string
  behind: number
} | null {
  const sessions = sessionsOf(rows)
  if (sessions.length < 2) return null
  const newest = sessions[0]
  return {
    newest,
    oldest: sessions[sessions.length - 1],
    // A row that carries no session is not counted: claiming it lags would be
    // a guess, and this number is shown to the reader as an exact count.
    behind: rows.filter((r) => r.lastSession && r.lastSession !== newest).length,
  }
}
