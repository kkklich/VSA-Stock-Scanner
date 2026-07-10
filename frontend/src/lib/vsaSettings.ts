// Shared VSA engine settings.
//
// The Scanner page edits these; every data hook serialises them into the
// `settings` query parameter, so the ranking, the charts and the back-test
// stats are all computed by the backend with the SAME detection rules the
// user configured. Persisted in localStorage.
//
// Defaults MUST mirror DEFAULT_SIGNAL_PARAMS in
// backend-python/app/analysis/vsa.py — when they match, the frontend omits
// the parameter entirely so the backend can serve its pre-warmed cache.

export type SignalId = 'spring' | 'sos' | 'test' | 'upthrust' | 'nodemand' | 'sow'

export interface SignalSettings {
  enabled: boolean
  /** Bar spread vs. 20-session average (min for wide bars, max for No Demand). */
  spreadMult: number
  /** Bar volume vs. average (min for high-volume, max for quiet signals). */
  volMult: number
  /** Where the close must sit in the bar's range, percent (0 = low, 100 = high). */
  closePos: number
  /** Sessions of rolling context (support/resistance + averages). */
  lookback: number
}

export type VsaSettings = Record<SignalId, SignalSettings>

export const SIGNAL_DEFAULTS: VsaSettings = {
  spring:   { enabled: true, spreadMult: 1.2, volMult: 1.2, closePos: 60, lookback: 20 },
  sos:      { enabled: true, spreadMult: 1.5, volMult: 1.5, closePos: 65, lookback: 20 },
  test:     { enabled: true, spreadMult: 1.0, volMult: 0.7, closePos: 65, lookback: 20 },
  upthrust: { enabled: true, spreadMult: 1.2, volMult: 1.3, closePos: 30, lookback: 20 },
  sow:      { enabled: true, spreadMult: 1.5, volMult: 1.5, closePos: 35, lookback: 20 },
  nodemand: { enabled: true, spreadMult: 0.7, volMult: 0.7, closePos: 65, lookback: 20 },
}

export const SIGNAL_IDS = Object.keys(SIGNAL_DEFAULTS) as SignalId[]

/* ── Horizon presets ─────────────────────────────────────────────────────── */

export type HorizonId = 'short' | 'mid' | 'long'

// Preset bundles for the three investment horizons. The horizon dial is the
// lookback — how much history defines "average" spread/volume and the
// support/resistance levels a signal must break:
//   short ≈ 10 sessions (~2 weeks)  — swing trading; reacts to local structure,
//                                     slightly looser volume/spread thresholds;
//   mid   ≈ 20 sessions (~1 month)  — the documented engine defaults;
//   long  ≈ 40 sessions (~2 months) — position trading; stricter thresholds so
//                                     only bars that stand out against months
//                                     of context qualify (fewer, stronger).
export const HORIZON_PRESETS: Record<HorizonId, VsaSettings> = {
  short: {
    spring:   { enabled: true, spreadMult: 1.2, volMult: 1.2, closePos: 60, lookback: 10 },
    sos:      { enabled: true, spreadMult: 1.4, volMult: 1.4, closePos: 65, lookback: 10 },
    test:     { enabled: true, spreadMult: 1.0, volMult: 0.7, closePos: 65, lookback: 10 },
    upthrust: { enabled: true, spreadMult: 1.2, volMult: 1.3, closePos: 30, lookback: 10 },
    sow:      { enabled: true, spreadMult: 1.4, volMult: 1.4, closePos: 35, lookback: 10 },
    nodemand: { enabled: true, spreadMult: 0.7, volMult: 0.7, closePos: 65, lookback: 10 },
  },
  // Mid term IS the default configuration — when active, the settings
  // parameter is omitted and the backend serves its pre-warmed cache.
  mid: SIGNAL_DEFAULTS,
  long: {
    spring:   { enabled: true, spreadMult: 1.3, volMult: 1.4, closePos: 65, lookback: 40 },
    sos:      { enabled: true, spreadMult: 1.7, volMult: 1.8, closePos: 70, lookback: 40 },
    test:     { enabled: true, spreadMult: 1.0, volMult: 0.6, closePos: 70, lookback: 40 },
    upthrust: { enabled: true, spreadMult: 1.3, volMult: 1.5, closePos: 25, lookback: 40 },
    sow:      { enabled: true, spreadMult: 1.7, volMult: 1.8, closePos: 30, lookback: 40 },
    nodemand: { enabled: true, spreadMult: 0.6, volMult: 0.6, closePos: 65, lookback: 40 },
  },
}

export const HORIZON_IDS: HorizonId[] = ['short', 'mid', 'long']

/** Deep-cloned settings for a horizon preset, safe to mutate in state. */
export function presetSettings(horizon: HorizonId): VsaSettings {
  const src = HORIZON_PRESETS[horizon]
  return Object.fromEntries(
    SIGNAL_IDS.map((id) => [id, { ...src[id] }]),
  ) as VsaSettings
}

function sameSignal(a: SignalSettings, b: SignalSettings): boolean {
  return (
    a.enabled === b.enabled &&
    a.spreadMult === b.spreadMult &&
    a.volMult === b.volMult &&
    a.closePos === b.closePos &&
    a.lookback === b.lookback
  )
}

/** Which horizon preset the settings exactly match, or null for custom. */
export function matchHorizon(settings: VsaSettings): HorizonId | null {
  for (const h of HORIZON_IDS) {
    if (SIGNAL_IDS.every((id) => sameSignal(settings[id], HORIZON_PRESETS[h][id]))) {
      return h
    }
  }
  return null
}

const STORAGE_KEY = 'stockpilot:vsa-settings:v2'
// Pre-v2 keys (scanner settings that never reached the backend) — cleaned up on load.
const LEGACY_KEYS = ['stockpilot:scanner:rules', 'stockpilot:scanner:params']

function cloneDefaults(): VsaSettings {
  return Object.fromEntries(
    SIGNAL_IDS.map((id) => [id, { ...SIGNAL_DEFAULTS[id] }]),
  ) as VsaSettings
}

/** Load saved settings, merging over defaults so new fields never go missing. */
export function loadVsaSettings(): VsaSettings {
  try {
    for (const k of LEGACY_KEYS) localStorage.removeItem(k)
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return cloneDefaults()
    const saved = JSON.parse(raw) as Partial<Record<SignalId, Partial<SignalSettings>>>
    const merged = cloneDefaults()
    for (const id of SIGNAL_IDS) {
      merged[id] = { ...merged[id], ...saved[id] }
    }
    return merged
  } catch {
    return cloneDefaults()
  }
}

export function saveVsaSettings(settings: VsaSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    /* storage full/blocked — settings simply won't persist */
  }
}

export function isDefaultSettings(settings: VsaSettings): boolean {
  return SIGNAL_IDS.every((id) => sameSignal(settings[id], SIGNAL_DEFAULTS[id]))
}

/**
 * The value for the `settings` API query parameter, or undefined when the
 * user has not changed anything (lets the backend serve its default cache).
 */
export function settingsQueryValue(settings?: VsaSettings): string | undefined {
  const current = settings ?? loadVsaSettings()
  if (isDefaultSettings(current)) return undefined
  return JSON.stringify(current)
}
