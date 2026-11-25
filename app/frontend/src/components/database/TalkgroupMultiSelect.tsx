import { useEffect, useMemo, useRef, useState } from 'react'

export interface TalkgroupMultiSelectProps {
  id?: string
  talkgroups: string[]
  selected: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
}

export function TalkgroupMultiSelect({
  id,
  talkgroups,
  selected,
  onChange,
  disabled = false,
}: TalkgroupMultiSelectProps) {
  const [open, setOpen] = useState(false)
  const [filterText, setFilterText] = useState('')
  const rootRef = useRef<HTMLDivElement | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!open) return
    const handleOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutside)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleOutside)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  useEffect(() => {
    if (open) {
      searchInputRef.current?.focus()
    } else {
      setFilterText('')
    }
  }, [open])

  const selectedSet = useMemo(() => new Set(selected), [selected])

  const filteredTalkgroups = useMemo(() => {
    const q = filterText.trim().toLowerCase()
    if (!q) return talkgroups
    return talkgroups.filter((tg) => tg.toLowerCase().includes(q))
  }, [filterText, talkgroups])

  const toggleOne = (tg: string) => {
    if (selectedSet.has(tg)) {
      onChange(selected.filter((item) => item !== tg))
    } else {
      onChange([...selected, tg])
    }
  }

  const selectVisible = () => {
    if (filteredTalkgroups.length === 0) return
    const nextSet = new Set(selected)
    for (const tg of filteredTalkgroups) {
      nextSet.add(tg)
    }
    onChange(Array.from(nextSet))
  }

  const triggerLabel =
    selected.length === 0
      ? 'All Talkgroups'
      : selected.length === 1
        ? selected[0]
        : `${selected.length} Talkgroups`

  return (
    <div className="relative" ref={rootRef}>
      <button
        id={id}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={selected.length > 0 ? selected.join(', ') : 'All Talkgroups'}
        onClick={() => setOpen((prev) => !prev)}
        className={`ss-input flex h-8 w-52 sm:w-64 items-center justify-between gap-2 text-left text-xs cursor-pointer transition-colors ${
          selected.length > 0 ? 'border-indigo-500/60 bg-indigo-500/[0.08] text-slate-100' : 'text-slate-200'
        }`}
      >
        <span className="truncate">{triggerLabel}</span>
        <svg
          viewBox="0 0 16 16"
          className={`h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          aria-multiselectable="true"
          className="absolute left-0 top-full z-40 mt-1 flex w-80 sm:w-96 flex-col rounded-sm border border-[#273147] bg-[#0e121c] shadow-2xl"
        >
          <div className="border-b border-[#1c2334] p-2">
            <input
              ref={searchInputRef}
              type="text"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Filter talkgroups…"
              aria-label="Filter talkgroups"
              className="ss-input h-7 w-full text-xs"
            />
          </div>

          <div className="flex items-center justify-between border-b border-[#1c2334] bg-[#121726] px-2.5 py-1.5 text-[11px] text-slate-400">
            <span className="font-mono">
              {selected.length === 0 ? 'All talkgroups' : `${selected.length} selected`}
            </span>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={selectVisible}
                disabled={filteredTalkgroups.length === 0}
                className="font-medium text-sky-400 hover:text-sky-300 disabled:opacity-40 cursor-pointer"
              >
                Select all
              </button>
              <button
                type="button"
                onClick={() => onChange([])}
                disabled={selected.length === 0}
                className="font-medium text-slate-300 hover:text-white disabled:opacity-40 cursor-pointer"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="max-h-72 overflow-y-auto p-1">
            {filteredTalkgroups.length === 0 ? (
              <p className="px-2 py-4 text-center text-xs text-slate-500">No matching talkgroups</p>
            ) : (
              filteredTalkgroups.map((tg) => {
                const isSelected = selectedSet.has(tg)
                return (
                  <label
                    key={tg}
                    className={`flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 transition-colors ${
                      isSelected ? 'bg-indigo-500/[0.09] text-slate-100' : 'text-slate-300 hover:bg-white/[0.05]'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleOne(tg)}
                      className="h-3.5 w-3.5 shrink-0 accent-indigo-500 cursor-pointer"
                    />
                    <span className="truncate text-xs" title={tg}>
                      {tg}
                    </span>
                  </label>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
