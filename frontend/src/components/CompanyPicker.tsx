// Company picker for the stock-detail header. Renders as plain heading text;
// clicking it turns into a searchable input with a dropdown of GPW companies.
// Choosing one navigates to /stock/:ticker. Falls back to navigating to a typed
// ticker when the company list can't be loaded.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, ChevronDown, Search } from 'lucide-react'
import { useCompanies } from '../hooks/useCompanies'

const MAX_RESULTS = 50

export function CompanyPicker({
  ticker,
  name,
}: {
  ticker: string
  name: string | null
}) {
  const navigate = useNavigate()
  const { companies, loading } = useCompanies()
  const [editing, setEditing] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q
      ? companies.filter(
          (c) =>
            c.ticker.toLowerCase().includes(q) ||
            c.name.toLowerCase().includes(q),
        )
      : companies
    return list.slice(0, MAX_RESULTS)
  }, [companies, query])

  // Focus the input when entering edit mode.
  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  // Close on outside click.
  useEffect(() => {
    if (!editing) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setEditing(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [editing])

  const open = () => {
    setQuery('')
    setHighlight(0)
    setEditing(true)
  }

  const choose = (nextTicker: string) => {
    setEditing(false)
    const t = nextTicker.trim().toLowerCase()
    if (t && t !== ticker.toLowerCase()) navigate(`/stock/${encodeURIComponent(t)}`)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const picked = results[highlight]
      if (picked) choose(picked.ticker)
      else if (query.trim()) choose(query) // fallback: go to the typed ticker
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setEditing(false)
    }
  }

  // ── Display mode: looks like the heading text, with a subtle affordance ──────
  if (!editing) {
    return (
      <button
        onClick={open}
        title="Click to change company"
        className="group inline-flex items-center gap-1.5 rounded-md px-1 -mx-1 text-left transition-colors hover:bg-slate-800/50"
      >
        <span className="text-xl font-bold text-slate-100">
          {name ?? ticker.toUpperCase()}
        </span>
        <span className="text-xl font-bold text-slate-500">
          ({ticker.toUpperCase()})
        </span>
        <ChevronDown
          size={16}
          className="text-slate-500 opacity-60 transition-opacity group-hover:opacity-100"
        />
      </button>
    )
  }

  // ── Edit mode: searchable input + dropdown ───────────────────────────────────
  return (
    <div ref={boxRef} className="relative">
      <div className="relative">
        <Search
          size={16}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
        />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setHighlight(0)
          }}
          onKeyDown={onKeyDown}
          placeholder={`${name ?? ticker.toUpperCase()} — type a name or ticker…`}
          className="w-72 max-w-[80vw] rounded-md border border-emerald-500/50 bg-slate-900 py-1.5 pl-8 pr-3 text-lg font-semibold text-slate-100 placeholder:text-sm placeholder:font-normal placeholder:text-slate-500 focus:outline-none"
        />
      </div>

      <ul className="absolute left-0 z-40 mt-1 max-h-72 w-80 max-w-[85vw] overflow-y-auto rounded-lg border border-slate-800 bg-slate-900 py-1 shadow-2xl">
        {results.map((c, i) => {
          const isCurrent = c.ticker.toLowerCase() === ticker.toLowerCase()
          return (
            <li key={c.ticker}>
              <button
                onMouseEnter={() => setHighlight(i)}
                onClick={() => choose(c.ticker)}
                className={
                  'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors ' +
                  (i === highlight ? 'bg-slate-800' : 'hover:bg-slate-800/60')
                }
              >
                <span className="min-w-0">
                  <span className="font-semibold text-slate-100">
                    {c.ticker.toUpperCase()}
                  </span>{' '}
                  <span className="text-slate-500">{c.name}</span>
                </span>
                {isCurrent && (
                  <Check size={14} className="shrink-0 text-emerald-400" />
                )}
              </button>
            </li>
          )
        })}

        {results.length === 0 && (
          <li className="px-3 py-3 text-center text-sm text-slate-500">
            {loading
              ? 'Loading companies…'
              : query.trim()
                ? `Press Enter to open “${query.trim().toUpperCase()}”`
                : 'No companies available.'}
          </li>
        )}
      </ul>
    </div>
  )
}
