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

  if (isMobile) {
    return (
      <div className="ss-panel ss-panel--stacked">
        <div className="ss-panel-pane">{left}</div>
        <div className="ss-panel-pane">{right}</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div ref={containerRef} className="ss-panel" style={{ height }}>
        <div className="flex flex-col overflow-hidden" style={{ width: `${leftPct}%`, flexShrink: 0 }}>
          {left}
        </div>

        {canResize && (
          <div onMouseDown={onColDown} className="ss-resize-col" role="separator" />
        )}
        {!canResize && <div className="w-px shrink-0 bg-white/10" aria-hidden />}

        <div className="flex flex-col overflow-hidden" style={{ flex: 1 }}>
          {right}
        </div>
      </div>

      {canResize && (
        <div onMouseDown={onRowDown} className="ss-resize-row" role="separator" />
      )}
    </div>
  )
}
