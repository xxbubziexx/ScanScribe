import { useEffect, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import type { HourActivityEntry, HourSummary } from '@/types/insights'
import { insights } from '@/lib/insights'

function hourToLabel(h: number) {
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h
  return `${h12}:00 ${h < 12 ? 'AM' : 'PM'}`
}

interface SummariesTabProps {
  date: string
}

export function SummariesTab({ date }: SummariesTabProps) {
  const [hours, setHours] = useState<HourActivityEntry[]>([])
  const [summaries, setSummaries] = useState<HourSummary[]>([])
  const [selectedHour, setSelectedHour] = useState<string>('')
  const [status, setStatus] = useState('Select an hour to generate.')
  const [loading, setLoading] = useState(false)
  const [openCards, setOpenCards] = useState<Set<number>>(new Set())

  const summaryMap = new Map(summaries.map((s) => [s.hour, s]))

  const loadAll = useCallback(async () => {
    try {
      const [hoursData, summariesData] = await Promise.all([
        insights.summaryHours(date),
        insights.summaries(date),
      ])
      setHours(hoursData.hours ?? [])
      setSummaries(summariesData.summaries ?? [])
    } catch {
      setHours([])
      setSummaries([])
    }
  }, [date])

  useEffect(() => {
    loadAll()
    setSelectedHour('')
    setStatus('Select an hour to generate.')
    setOpenCards(new Set())
  }, [date, loadAll])

  useEffect(() => {
    const h = selectedHour !== '' ? parseInt(selectedHour) : null
    if (h === null) {
      setStatus('Select an hour to generate.')
    } else if (summaryMap.has(h)) {
      setStatus(`Summary exists for ${hourToLabel(h)}.`)
    } else {
      setStatus(`No summary yet for ${hourToLabel(h)}.`)
    }
  }, [selectedHour, summaries]) // eslint-disable-line react-hooks/exhaustive-deps

  async function generate(force: boolean) {
    const h = selectedHour !== '' ? parseInt(selectedHour) : null
    if (h === null) { setStatus('Select an hour first.'); return }
    setLoading(true)
    setStatus(force ? 'Regenerating…' : 'Generating…')
    try {
      await insights.generateSummary(date, h, force)
      await loadAll()
      setStatus(`Saved summary for ${hourToLabel(h)}.`)
    } catch (e: unknown) {
      setStatus((e as Error).message ?? 'Failed to generate summary.')
    } finally {
      setLoading(false)
    }
  }

  async function deleteSummary() {
    const h = selectedHour !== '' ? parseInt(selectedHour) : null
    if (h === null) { setStatus('Select an hour first.'); return }
    setLoading(true)
    setStatus('Deleting…')
    try {
      await insights.deleteSummary(date, h)
      await loadAll()
      setStatus(`Deleted summary for ${hourToLabel(h)}.`)
    } catch {
      setStatus('Failed to delete summary.')
    } finally {
      setLoading(false)
    }
  }

  function toggleCard(hour: number) {
    setOpenCards((prev) => {
      const next = new Set(prev)
      next.has(hour) ? next.delete(hour) : next.add(hour)
      return next
    })
  }

  return (
    <div>
      {/* Controls row */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium text-gray-300">Hour Summary</p>
        <p className="text-xs text-gray-500">{status}</p>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={selectedHour}
          onChange={(e) => setSelectedHour(e.target.value)}
          className="ss-select min-w-[200px]"
        >
          <option value="">Hours with activity…</option>
          {hours.map((h) => (
            <option key={h.hour} value={h.hour}>
              {hourToLabel(h.hour)} ({h.count})
            </option>
          ))}
        </select>

        <button
          onClick={() => generate(false)}
          disabled={loading || selectedHour === ''}
          className="ss-btn-primary"
        >
          Generate
        </button>
        <button
          onClick={() => generate(true)}
          disabled={loading || selectedHour === ''}
          className="ss-btn-ghost-bright"
        >
          Regenerate
        </button>
        <button
          onClick={deleteSummary}
          disabled={loading || selectedHour === '' || !summaryMap.has(parseInt(selectedHour))}
          className="ss-btn-danger-soft"
        >
          Delete
        </button>
      </div>

      {/* Summaries list */}
      {summaries.length === 0 ? (
        <p className="text-sm text-gray-500">No summaries saved for this day.</p>
      ) : (
        <div className="space-y-2">
          {summaries.map((s) => {
            const isOpen = openCards.has(s.hour)
            const ts = s.updated_at || s.created_at
            return (
              <div
                key={s.hour}
                className="ss-summaries-card"
              >
                <button
                  onClick={() => toggleCard(s.hour)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                >
                  <span className="text-sm font-medium text-gray-200">
                    {hourToLabel(s.hour)}
                  </span>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{s.updated_at ? 'Updated' : 'Created'} {ts}</span>
                    <span className="text-gray-600">{isOpen ? '▼' : '▶'}</span>
                  </div>
                </button>
                {isOpen && (
                  <div className="prose prose-sm prose-invert ss-md-body">
                    <ReactMarkdown>{s.text}</ReactMarkdown>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
