import { useCallback, useMemo, useRef, type SetStateAction } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

export interface UrlField<T> {
  read: (params: URLSearchParams, key: string) => T
  write: (params: URLSearchParams, key: string, value: T) => void
}

export function textParam(fallback = ''): UrlField<string> {
  return {
    read: (params, key) => params.get(key) ?? fallback,
    write: (params, key, value) => {
      if (value === fallback) params.delete(key)
      else params.set(key, value)
    },
  }
}

export function enumParam<T extends string>(fallback: T, values: readonly T[]): UrlField<T> {
  return {
    ...textParam(fallback),
    read: (params, key) => {
      const value = params.get(key) as T
      return values.includes(value) ? value : fallback
    },
  }
}

export function booleanParam(fallback = false): UrlField<boolean> {
  return {
    read: (params, key) => {
      const value = params.get(key)
      return value === '1' || value === 'true' ? true
        : value === '0' || value === 'false' ? false : fallback
    },
    write: (params, key, value) => {
      if (value === fallback) params.delete(key)
      else params.set(key, value ? '1' : '0')
    },
  }
}

interface NumberOptions {
  min?: number; max?: number; integer?: boolean; values?: readonly number[]
}
export function numberParam(fallback: number, options?: NumberOptions): UrlField<number>
export function numberParam(fallback: null, options?: NumberOptions): UrlField<number | null>
export function numberParam(
  fallback: number | null,
  { min = 0, max = Infinity, integer = false, values }: NumberOptions = {},
): UrlField<number> | UrlField<number | null> {
  return {
    read: (params, key) => {
      const raw = params.get(key)
      const value = raw?.trim() ? Number(raw) : NaN
      return Number.isFinite(value) && value >= min && value <= max
        && (!integer || Number.isInteger(value)) && (!values || values.includes(value))
        ? value : fallback
    },
    write: (params: URLSearchParams, key: string, value: number | null) => {
      if (value === fallback || value === null) params.delete(key)
      else params.set(key, String(value))
    },
  }
}

type Schema<T> = { [K in keyof T]: UrlField<T[K]> }

/** The URL owns list state, including reloads and browser Back/Forward. */
export function useUrlState<T extends object>(schema: Schema<T>) {
  const location = useLocation()
  const navigate = useNavigate()
  const state = useMemo(() => {
    const params = new URLSearchParams(location.search)
    return Object.fromEntries(Object.entries(schema).map(([key, codec]) =>
      [key, (codec as UrlField<unknown>).read(params, key)],
    )) as T
  }, [location.search, schema])
  // A draft lets several setters in one event (e.g. Clear filters) compose.
  const searchAtRender = location.search.replace(/^\?/, '')
  const draft = useRef({ location, state, search: searchAtRender })
  if (draft.current.location !== location) draft.current = { location, state, search: searchAtRender }

  const setState = useCallback((action: SetStateAction<T>, replace = false) => {
    const previous = draft.current.state
    const next = typeof action === 'function' ? (action as (prev: T) => T)(previous) : action
    const params = new URLSearchParams(location.search)
    for (const key of Object.keys(schema) as (keyof T & string)[]) {
      schema[key].write(params, key, next[key])
    }
    const search = params.toString()
    if (search === draft.current.search) return
    draft.current.state = next
    draft.current.search = search
    navigate({ pathname: location.pathname, search, hash: location.hash }, { replace, preventScrollReset: true })
  }, [location, navigate, schema])

  function field<K extends keyof T>(key: K) {
    const set = (action: SetStateAction<T[K]>, replace = false) => setState((previous) => ({
      ...previous,
      [key]: typeof action === 'function'
        ? (action as (prev: T[K]) => T[K])(previous[key]) : action,
    }), replace)
    return [state[key], set] as const
  }
  return { state, setState, field }
}
