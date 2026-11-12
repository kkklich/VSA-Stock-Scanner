import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { addFilterPresets, getFilterPresets } from '../api/filterPresetsApi'
import { createPreset, EMPTY_FILTERS, savePresets, type FilterPreset } from '../lib/filterPresets'
import { useFilterPresets } from './useFilterPresets'

const auth = vi.hoisted(() => ({ user: { id: 1 } as { id: number } | null, loading: false }))
vi.mock('./useAuth', () => ({ useAuth: () => auth }))
vi.mock('../api/filterPresetsApi', () => ({
  getFilterPresets: vi.fn(), addFilterPresets: vi.fn(), deleteFilterPreset: vi.fn(),
}))

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  auth.user = { id: 1 }
  auth.loading = false
})

it('ignores a late save from a previous account, including after signing back into the same account', async () => {
  const original = createPreset('Original', EMPTY_FILTERS)
  const saved = createPreset('Late response', EMPTY_FILTERS)
  const browser = createPreset('Browser', EMPTY_FILTERS)
  savePresets([browser])
  vi.mocked(getFilterPresets).mockResolvedValue([original])
  let resolveSave!: (presets: FilterPreset[]) => void
  vi.mocked(addFilterPresets).mockImplementationOnce(() => new Promise(resolve => { resolveSave = resolve }))
  const { result, rerender } = renderHook(useFilterPresets)
  await waitFor(() => expect(result.current.presets).toEqual([original]))
  let save!: Promise<boolean>
  act(() => { save = result.current.save(saved) })
  const [, expectedOwner, signal] = vi.mocked(addFilterPresets).mock.calls[0]
  expect(expectedOwner).toBe(1)
  auth.user = null
  rerender()
  expect(signal?.aborted).toBe(true)
  expect(result.current.presets).toEqual([browser])
  auth.user = { id: 1 }
  rerender()
  await waitFor(() => expect(result.current.presets).toEqual([original]))
  await act(async () => {
    resolveSave([saved])
    expect(await save).toBe(false)
  })
  expect(result.current.presets).toEqual([original])
})

it('leaves browser data intact after a failed copy; retries only missing preset IDs', async () => {
  const first = createPreset('Imported', EMPTY_FILTERS)
  const second = createPreset('Local', EMPTY_FILTERS)
  savePresets([first, second])
  vi.mocked(getFilterPresets).mockResolvedValue([first])
  vi.mocked(addFilterPresets)
    .mockRejectedValueOnce(new Error('network'))
    .mockResolvedValueOnce([second, first])
  const { result, rerender } = renderHook(useFilterPresets)
  await waitFor(() => expect(result.current.importableCount).toBe(1))
  await act(async () => { expect(await result.current.importLocal()).toBe(false) })
  expect(result.current.error).toBe('failed')
  expect(result.current.presets).toEqual([first])
  await act(async () => { expect(await result.current.importLocal()).toBe(true) })
  expect(result.current.importableCount).toBe(0)
  expect(vi.mocked(addFilterPresets).mock.calls.map(call => call[0])).toEqual([[second], [second]])
  auth.user = null
  rerender()
  expect(result.current.presets).toEqual([first, second])
})

it('keeps both account and browser presets hidden and disables writes while restoring the session', async () => {
  const guestPreset = createPreset('Guest', EMPTY_FILTERS)
  savePresets([guestPreset])
  auth.user = null
  auth.loading = true
  const { result } = renderHook(useFilterPresets)
  expect(result.current.presets).toEqual([])
  expect(result.current.busy).toBe(true)
  expect(await result.current.save(guestPreset)).toBe(false)
  expect(getFilterPresets).not.toHaveBeenCalled()
  expect(addFilterPresets).not.toHaveBeenCalled()
})

it.each([
  new ApiError(409, 'changed', 'account_changed'),
  new ApiError(401, 'signed out'),
])('hides cached private presets when the session changes: %s', async (error) => {
  const first = createPreset('Private to A', EMPTY_FILTERS)
  vi.mocked(getFilterPresets).mockResolvedValueOnce([first])
  vi.mocked(addFilterPresets).mockRejectedValueOnce(error)
  const { result } = renderHook(useFilterPresets)
  await waitFor(() => expect(result.current.presets).toEqual([first]))
  await act(async () => { expect(await result.current.save(first)).toBe(false) })
  expect(result.current.presets).toEqual([])
  expect(result.current.busy).toBe(true)
  expect(result.current.error).toBe('account_changed')
})

it('refreshes saves and deletions made on a second device when the tab regains focus', async () => {
  const preset = createPreset('From phone', EMPTY_FILTERS)
  vi.mocked(getFilterPresets)
    .mockResolvedValueOnce([]).mockResolvedValueOnce([preset]).mockResolvedValueOnce([])
  const { result } = renderHook(useFilterPresets)
  await waitFor(() => expect(result.current.busy).toBe(false))
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  expect(result.current.presets).toEqual([preset])
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  expect(result.current.presets).toEqual([])
  expect(getFilterPresets).toHaveBeenCalledTimes(3)
})
