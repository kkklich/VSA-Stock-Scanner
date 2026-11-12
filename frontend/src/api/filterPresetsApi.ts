import type { FilterPreset } from '../lib/filterPresets'
import { apiFetch } from './client'

const endpoint = '/api/filter-presets'

// Another tab can switch the bearer token before this tab's UI learns about
// the change. Let the server check which account the caller actually saw.
function accountHeaders(owner: number) {
  return { 'X-Expected-User-Id': String(owner) }
}

export function getFilterPresets(owner: number, signal: AbortSignal) {
  return apiFetch<FilterPreset[]>(endpoint, { signal, headers: accountHeaders(owner) })
}

export function addFilterPresets(presets: FilterPreset[], owner: number, signal: AbortSignal) {
  return apiFetch<FilterPreset[]>(endpoint, {
    method: 'POST', body: JSON.stringify({ presets }), signal, headers: accountHeaders(owner),
  })
}

export function deleteFilterPreset(id: string, owner: number, signal: AbortSignal) {
  return apiFetch<FilterPreset[]>(`${endpoint}/${encodeURIComponent(id)}`, {
    method: 'DELETE', signal, headers: accountHeaders(owner),
  })
}
