// "Methods" multi-select dropdown for the dashboard. Lists every available
// trading method (VSA + the pluggable ones) with a link to its source, and
// lets the user choose which ones appear as columns. The plain-language
// description sits behind the row's info icon so the list stays scannable.
// Selection is owned by the page (persisted in localStorage); this component
// is presentational.

import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Info, Layers, RotateCcw } from 'lucide-react'
import type { ApiTradingMethod } from '../api/stocksApi'

/**
 * Info icon that reveals a method's description on hover or keyboard focus.
 * The tooltip uses fixed viewport coordinates rather than `absolute` because
 * the method list scrolls (`overflow-y-auto`), which would otherwise clip it.
 * It sits beside the dropdown (never on top of it) and drops below the whole
 * panel when the screen is too narrow for that.
 */
function MethodInfoTip({
  text,
  panelRef,
}: {
  text: string
  /** The dropdown panel, so the tooltip can clear it instead of covering it. */
  panelRef: RefObject<HTMLDivElement | null>
}) {
  const { t } = useTranslation()
  const [style, setStyle] = useState<CSSProperties | null>(null)

  // Scrolling or resizing moves the icon away from the measured rect, so drop
  // the tooltip instead of leaving it floating in the wrong place.
  useEffect(() => {
    if (!style) return
    const close = () => setStyle(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [style])

  const show = (e: { currentTarget: HTMLElement }) =>
    setStyle(
      tooltipPosition(
        e.currentTarget.getBoundingClientRect(),
        panelRef.current?.getBoundingClientRect() ?? null,
      ),
    )

  return (
    <>
      <button
        type="button"
        aria-label={t('common.moreInfo')}
        onMouseEnter={show}
        onMouseLeave={() => setStyle(null)}
        onFocus={show}
        onBlur={() => setStyle(null)}
        className="mt-0.5 shrink-0 text-slate-500 transition-colors hover:text-slate-300 focus:text-slate-300 focus:outline-none"
      >
        <Info size={14} />
      </button>
      {style &&
        createPortal(
          // Rendered on <body> so the tooltip is never painted under the
          // sidebar or another overlay if it has to overlap one.
          <span
            role="tooltip"
            style={style}
            className="pointer-events-none z-[60] rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs leading-relaxed text-slate-200 shadow-xl"
          >
            {text}
          </span>,
          document.body,
        )}
    </>
  )
}

/** Viewport coordinates for a tooltip anchored to the icon at `icon`. */
function tooltipPosition(icon: DOMRect, panel: DOMRect | null): CSSProperties {
  const gap = 8
  const width = 288
  const box = panel ?? icon
  // Level with the icon, anchored to whichever edge keeps the tooltip (whose
  // height we don't know yet) inside the viewport.
  const vertical =
    icon.top > window.innerHeight / 2
      ? { bottom: Math.max(gap, window.innerHeight - icon.bottom - gap) }
      : { top: Math.max(gap, icon.top - gap) }

  if (window.innerWidth - box.right >= width + gap * 2) {
    return { position: 'fixed', width, left: box.right + gap, ...vertical }
  }
  if (box.left >= width + gap * 2) {
    return { position: 'fixed', width, right: window.innerWidth - box.left + gap, ...vertical }
  }
  // Too narrow to fit beside the dropdown — go under it, so the list of
  // methods stays readable while the description is up.
  return { position: 'fixed', left: gap, right: gap, top: box.bottom + gap }
}

export function MethodPicker({
  methods,
  selected,
  onToggle,
  onReset,
  customized,
}: {
  methods: ApiTradingMethod[]
  /** Currently selected method ids. */
  selected: string[]
  onToggle: (id: string) => void
  onReset: () => void
  /** Whether the selection differs from the default (all methods). */
  customized: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const selectedSet = new Set(selected)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={
          'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ' +
          (customized
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
            : 'border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800')
        }
        aria-haspopup="true"
        aria-expanded={open}
        title={t('methods.title')}
      >
        <Layers size={14} />
        <span className="hidden sm:inline">{t('methods.button')}</span>
        <span className="rounded bg-slate-800/80 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-400">
          {selected.length}
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            ref={panelRef}
            className="absolute right-0 z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-800 bg-slate-900 p-2 shadow-xl"
          >
            <div className="flex items-center justify-between px-2 py-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                {t('methods.heading')}
              </span>
              <button
                type="button"
                onClick={onReset}
                disabled={!customized}
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                title={t('methods.showAll')}
              >
                <RotateCcw size={11} /> {t('methods.all')}
              </button>
            </div>

            <div className="max-h-96 overflow-y-auto">
              {methods.map((m) => {
                const checked = selectedSet.has(m.id)
                return (
                  <div
                    key={m.id}
                    className="flex items-start gap-2 rounded-md px-2 py-2 transition-colors hover:bg-slate-800"
                  >
                    <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-2.5 text-sm">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggle(m.id)}
                        className="mt-0.5 h-3.5 w-3.5 rounded border-slate-600 bg-slate-950 text-emerald-500 accent-emerald-500 focus:ring-0"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-medium text-slate-200">{m.name}</span>
                        <span className="mt-0.5 block text-[11px] text-slate-600">
                          {t('methods.source')}{' '}
                          {m.sourceUrl ? (
                            <a
                              href={m.sourceUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-slate-400 underline decoration-slate-700 underline-offset-2 hover:text-slate-200"
                            >
                              {m.source}
                            </a>
                          ) : (
                            <span className="text-slate-500">{m.source}</span>
                          )}
                        </span>
                      </span>
                    </label>
                    <MethodInfoTip text={m.description} panelRef={panelRef} />
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
