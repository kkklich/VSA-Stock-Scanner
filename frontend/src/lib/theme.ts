// Light / dark theme: the single source of truth for which theme is active.
//
// The user picks one of three settings — 'dark' (the app's default and its
// original look), 'light', or 'system' (follow the operating system). The
// choice is stored in localStorage and applied by putting (or removing) the
// class `dark` on <html>; every colour in the app is a CSS variable that
// switches with that class (see `src/index.css`).
//
// The very first application happens *before React runs*, in a tiny inline
// script in `index.html`, so the page never flashes the wrong theme. That
// script and `paint` below must stay in agreement — the key name, the
// class name and the default are repeated there deliberately.
//
// Components that cannot use CSS variables (the TradingView charts, the
// heatmap tiles, inline SVG) read the resolved theme with `useResolvedTheme()`
// and re-render themselves when it changes.

import { useSyncExternalStore } from 'react'

/** What the user chose. 'system' follows the OS setting. */
export type ThemePreference = 'light' | 'dark' | 'system'
/** What is actually on screen once 'system' has been resolved. */
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'stockpilot:theme'

/** The app ships dark; light is the opt-in. */
export const DEFAULT_THEME: ThemePreference = 'dark'

export const THEME_PREFERENCES: ThemePreference[] = ['light', 'dark', 'system']

/** Used when 'system' is chosen but the browser cannot report a preference. */
const SYSTEM_FALLBACK: ResolvedTheme = 'dark'

/** Browser chrome colour (address bar on mobile) per theme. */
const META_THEME_COLOR: Record<ResolvedTheme, string> = {
  dark: '#020617', // slate-950
  light: '#eef2f7',
}

function isPreference(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

/** The stored choice, or the default when nothing valid is stored. */
export function readStoredTheme(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    return isPreference(raw) ? raw : DEFAULT_THEME
  } catch {
    // Private mode / storage disabled — fall back to the default.
    return DEFAULT_THEME
  }
}

/** What the OS asks for. Defaults to the app default where unsupported. */
function systemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return SYSTEM_FALLBACK
  }
  return window.matchMedia('(prefers-color-scheme: light)').matches
    ? 'light'
    : 'dark'
}

/** Turn a preference into the theme that should actually be shown. */
export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === 'system' ? systemTheme() : preference
}

// ── Applying the theme to the document ────────────────────────────────────────

/** Put the resolved theme on <html> (class + meta theme-color). */
function paint(resolved: ResolvedTheme) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', resolved === 'dark')
  document.documentElement.dataset.theme = resolved
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', META_THEME_COLOR[resolved])
}

// ── A tiny store so every component sees the same theme ───────────────────────

let preference: ThemePreference = DEFAULT_THEME
let resolved: ResolvedTheme = resolveTheme(DEFAULT_THEME)
const listeners = new Set<() => void>()

/**
 * The OS colour-scheme query, held at module level on purpose: a MediaQueryList
 * that nothing references can be garbage-collected along with its listener, and
 * "System" would then quietly stop following the OS.
 */
let systemQuery: MediaQueryList | null = null

function notify() {
  for (const listener of listeners) listener()
}

/**
 * Load the stored preference and apply it. Called once from `main.tsx`; safe to
 * call again (the inline script in index.html has usually done the painting
 * already, and this simply confirms it).
 */
export function initTheme() {
  setThemePreference(readStoredTheme(), { persist: false })

  // Keep 'system' honest: react to the OS flipping while the app is open.
  if (
    systemQuery === null &&
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function'
  ) {
    systemQuery = window.matchMedia('(prefers-color-scheme: light)')
    const onChange = () => {
      if (preference !== 'system') return
      resolved = systemTheme()
      paint(resolved)
      notify()
    }
    // Safari < 14 only has the deprecated addListener.
    if (typeof systemQuery.addEventListener === 'function') {
      systemQuery.addEventListener('change', onChange)
    } else if (typeof systemQuery.addListener === 'function') {
      systemQuery.addListener(onChange)
    }
  }
}

/** Change the theme (and remember it). */
export function setThemePreference(
  next: ThemePreference,
  options: { persist?: boolean } = {},
) {
  preference = next
  resolved = resolveTheme(next)
  paint(resolved)
  if (options.persist !== false) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      /* ignore quota / private-mode errors */
    }
  }
  notify()
}

export function getThemePreference(): ThemePreference {
  return preference
}

export function getResolvedTheme(): ResolvedTheme {
  return resolved
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

// ── React hooks ───────────────────────────────────────────────────────────────

/**
 * The theme the user picked plus a setter — for the toggle and the Settings
 * page. `resolved` says which of the two themes that currently means.
 */
export function useTheme() {
  const preferenceValue = useSyncExternalStore(
    subscribe,
    getThemePreference,
    getThemePreference,
  )
  const resolvedValue = useSyncExternalStore(
    subscribe,
    getResolvedTheme,
    getResolvedTheme,
  )
  return {
    preference: preferenceValue,
    resolved: resolvedValue,
    setPreference: setThemePreference,
  }
}

/**
 * Just the active theme, for components that paint themselves in JavaScript
 * (charts, heatmap tiles, inline SVG) and so must redraw when it changes.
 */
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, getResolvedTheme, getResolvedTheme)
}
