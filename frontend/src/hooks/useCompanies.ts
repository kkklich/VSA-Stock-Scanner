// Custom hook: fetch the tracked GPW company list once. The list is static
// seed data on the backend, so it works even when the ranking feed is down —
// which is what makes it a reliable source for the company picker.

import { useEffect, useState } from 'react'
import { fetchCompanies, type ApiCompany } from '../api/stocksApi'

export interface UseCompaniesResult {
  companies: ApiCompany[]
  loading: boolean
  error: string | null
}

export function useCompanies(): UseCompaniesResult {
  const [companies, setCompanies] = useState<ApiCompany[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchCompanies()
      .then((list) => {
        if (!cancelled) {
          setCompanies(list)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unknown error')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { companies, loading, error }
}
