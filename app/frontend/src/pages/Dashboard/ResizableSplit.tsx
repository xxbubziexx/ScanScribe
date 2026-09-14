import { useCallback, useEffect, useRef, useState } from 'react'

interface ResizableSplitProps {
  left: React.ReactNode
  right: React.ReactNode
  defaultLeftPct?: number
  defaultHeight?: number
  minLeftPct?: number
  maxLeftPct?: number
  minHeight?: number
  /** When false, fixed size and no drag handles. */
  resizable?: boolean
}

const MOBILE_MQ = '(max-width: 767px)'

export function ResizableSplit({
  left,
  right,
  defaultLeftPct = 55,
  defaultHeight = 1000,
  minLeftPct = 20,
  maxLeftPct = 80,
  minHeight = 300,
  resizable = true,
}: ResizableSplitProps) {
  const [leftPct, setLeftPct] = useState(defaultLeftPct)
  const [height, setHeight] = useState(defaultHeight)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(MOBILE_MQ).matches : false,
  )

  const containerRef = useRef<HTMLDivElement>(null)
  const draggingCol = useRef(false)
  const draggingRow = useRef(false)

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MQ)
    const onChange = () => setIsMobile(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const canResize = resizable && !isMobile

  const onColDown = useCallback(
    (e: React.MouseEvent) => {
      if (!canResize) return
      e.preventDefault()
      draggingCol.current = true
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    },
    [canResize],
  )

  const onRowDown = useCallback(
    (e: React.MouseEvent) => {
      if (!canResize) return
      e.preventDefault()
      draggingRow.current = true
      document.body.style.cursor = 'row-resize'
      document.body.style.userSelect = 'none'
    },
    [canResize],
  )

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (draggingCol.current && containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        const pct = ((e.clientX - rect.left) / rect.width) * 100
        if (pct > minLeftPct && pct < maxLeftPct) setLeftPct(pct)
      }
      if (draggingRow.current && containerRef.current) {
        const parent = containerRef.current.parentElement
        if (!parent) return
        const rect = parent.getBoundingClientRect()
        const newH = e.clientY - rect.top
        if (newH > minHeight) setHeight(newH)
      }
    }

    function onMouseUp() {
      if (draggingCol.current || draggingRow.current) {
        draggingCol.current = false
        draggingRow.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [minLeftPct, maxLeftPct, minHeight])

  const [mobileTab, setMobileTab] = useState<'transcriptions' | 'console'>('transcriptions')

  if (isMobile) {
    return (
      <div className="ss-panel ss-panel--stacked flex flex-col">
        {/* Mobile View Switcher */}
        <div
          className="p-2 border-b border-white/10 bg-white/[0.02]"
          role="tablist"
          aria-label="Dashboard views"
        >
          <div className="grid grid-cols-2 bg-white/5 p-1 rounded-xl border border-white/10 w-full gap-1">
            <button
              type="button"
              role="tab"
              aria-selected={mobileTab === 'transcriptions'}
              className={`flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold rounded-lg transition min-h-[42px] cursor-pointer ${
                mobileTab === 'transcriptions'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
              onClick={() => setMobileTab('transcriptions')}
            >
              <span>📻</span>
              <span>Transcriptions</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mobileTab === 'console'}
              className={`flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold rounded-lg transition min-h-[42px] cursor-pointer ${
                mobileTab === 'console'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
              onClick={() => setMobileTab('console')}
            >
              <span>💻</span>
              <span>Console</span>
            </button>
          </div>
        </div>

        <div className="ss-panel-pane flex-1 min-h-[440px]">
          {mobileTab === 'transcriptions' ? left : right}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div ref={containerRef} className="ss-panel" style={{ height }}>
        <div
          className="flex flex-col overflow-hidden"
          style={{ width: `${leftPct}%`, flexShrink: 0 }}
        >
          {left}
        </div>

        {canResize && <div onMouseDown={onColDown} className="ss-resize-col" role="separator" />}
        {!canResize && <div className="w-px shrink-0 bg-white/10" aria-hidden />}

        <div className="flex flex-col overflow-hidden" style={{ flex: 1 }}>
          {right}
        </div>
      </div>

      {canResize && <div onMouseDown={onRowDown} className="ss-resize-row" role="separator" />}
    </div>
  )
}
