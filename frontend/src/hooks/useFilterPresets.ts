import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { addFilterPresets, deleteFilterPreset, getFilterPresets } from '../api/filterPresetsApi'
import { FILTER_PRESETS_KEY, loadPresets, savePresets, type FilterPreset } from '../lib/filterPresets'
import { useAuth } from './useAuth'

type PresetRequest = (owner: number, signal: AbortSignal) => Promise<FilterPreset[]>
const presetErrorCodes = new Set(['preset_limit', 'id_conflict', 'not_found', 'account_changed'])

function failureCode(error: unknown): string {
  if (!(error instanceof ApiError)) return 'failed'
  if (error.status === 401) return 'account_changed'
  if (error.code && presetErrorCodes.has(error.code)) return error.code
  return error.status === 422 ? 'invalid' : 'failed'
}

export function useFilterPresets() {
  const { user, loading: checkingSession } = useAuth()
  const owner = user?.id ?? null
  const [local, setLocal] = useState(loadPresets)
  const [account, setAccount] = useState<{ owner: number; presets: FilterPreset[] } | null>(null)
  const [failure, setFailure] = useState<{ owner: number | null; code: string } | null>(null)
  const [pending, setPending] = useState(false)
  const active = useRef<AbortController | null>(null)
  const currentOwner = useRef(owner)
  currentOwner.current = owner

  // Serialize reads and mutations so a slow refresh cannot undo a saved or
  // deleted preset in the UI. Each mutation returns the entire account list.
  const run = useCallback(async (request: PresetRequest) => {
    if (owner === null || currentOwner.current !== owner || checkingSession || active.current) return false
    const controller = new AbortController()
    active.current = controller
    setPending(true)
    try {
      const presets = await request(owner, controller.signal)
      if (controller.signal.aborted || currentOwner.current !== owner) return false
      setAccount({ owner, presets })
      setFailure(null)
      return true
    } catch (error) {
      if (!controller.signal.aborted && currentOwner.current === owner) {
        const code = failureCode(error)
        if (code === 'account_changed') setAccount(null)
        setFailure({ owner, code })
      }
      return false
    } finally {
      if (active.current === controller) {
        active.current = null
        setPending(false)
      }
    }
  }, [owner, checkingSession])

  useEffect(() => {
    setPending(false)
    setFailure(null)
    setAccount(null)
    if (checkingSession || owner === null) return
    void run(getFilterPresets)
    const refresh = () => { if (!document.hidden) void run(getFilterPresets) }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    const timer = window.setInterval(refresh, 60_000)
    return () => {
      active.current?.abort()
      active.current = null
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
      window.clearInterval(timer)
    }
  }, [owner, checkingSession, run])

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === FILTER_PRESETS_KEY || event.key === null) setLocal(loadPresets())
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  const ready = !checkingSession && owner !== null && account?.owner === owner
  const guest = !checkingSession && owner === null
  const presets = guest ? local : ready ? account.presets : []
  const error = failure?.owner === owner ? failure.code : null
  const copied = new Set(presets.map(preset => preset.id))
  const importable = ready ? local.filter(preset => !copied.has(preset.id)) : []

  const updateLocal = (edit: (previous: FilterPreset[]) => FilterPreset[]) => {
    if (!guest || currentOwner.current !== null) return false
    const next = edit(loadPresets())
    if (!savePresets(next)) {
      setFailure({ owner: null, code: 'storage' })
      return false
    }
    setFailure(null)
    setLocal(next)
    return true
  }

  return {
    owner, presets, error, importableCount: importable.length,
    loading: checkingSession || (owner !== null && !ready && !error),
    busy: checkingSession || pending || (owner !== null && !ready),
    reload: () => {
      if (guest) {
        setLocal(loadPresets())
        setFailure(null)
      } else {
        void run(getFilterPresets)
      }
    },
    save: async (preset: FilterPreset) => guest
      ? updateLocal(previous => [...previous, preset])
      : ready && run((userId, signal) => addFilterPresets([preset], userId, signal)),
    remove: async (id: string) => guest
      ? updateLocal(previous => previous.filter(preset => preset.id !== id))
      : ready && run((userId, signal) => deleteFilterPreset(id, userId, signal)),
    importLocal: async () => importable.length > 0 && run((userId, signal) => addFilterPresets(importable, userId, signal)),
  }
}
