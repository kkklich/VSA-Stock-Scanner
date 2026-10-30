import { renderHook, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useMethods } from './useMethods'

vi.mock('../api/stocksApi', () => ({
  fetchMethods: async () => (
    ['vsa', 'vsa3', 'glinicki', 'vsa4', 'minervini'].map((id) => ({ id, name: id }))
  ),
}))

it('filters archived entries even when an older server advertises them', async () => {
  const { result } = renderHook(useMethods)
  await waitFor(() => expect(result.current.loading).toBe(false))
  expect(result.current.methods.map((m) => m.id)).toEqual(['vsa4', 'minervini'])
})
