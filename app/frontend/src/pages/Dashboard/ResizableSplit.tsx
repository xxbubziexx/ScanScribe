import { useCallback, useEffect, useRef, useState } from 'react'

interface ResizableSplitProps {
  left: React.ReactNode
  right: React.ReactNode
  defaultLeftPct?: number
  defaultHeight?: number
  minLeftPct?: number
  maxLeftPct?: number
  minHeight?: number
}

export function ResizableSplit({
  left,
  right,
  defaultLeftPct = 55,
  defaultHeight = 1000,
  minLeftPct = 20,
  maxLeftPct = 80,
  minHeight = 300,
}: ResizableSplitProps) {
  const [leftPct, setLeftPct] = useState(defaultLeftPct)
  const [height, setHeight] = useState(defaultHeight)

  const containerRef = useRef<HTMLDivElement>(null)
  const draggingCol = useRef(false)
  const draggingRow = useRef(false)

  const onColDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    draggingCol.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  const onRowDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    draggingRow.current = true
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'
  }, [])

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
        // newH is parent-relative; do not cap with window.innerHeight - N alone — that
        // rejects all drags when defaultHeight is already >= that (slider appears "dead").
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

  return (
    <div className="flex flex-col">
      {/* Horizontal split */}
      <div ref={containerRef} className="ss-panel" style={{ height }}>
        {/* Left pane */}
        <div className="flex flex-col overflow-hidden" style={{ width: `${leftPct}%`, flexShrink: 0 }}>
          {left}
        </div>

        {/* Column drag handle */}
        <div onMouseDown={onColDown} className="ss-resize-col" role="separator" />

        {/* Right pane */}
        <div className="flex flex-col overflow-hidden" style={{ flex: 1 }}>
          {right}
        </div>
      </div>

      {/* Row drag handle (height resizer) */}
      <div onMouseDown={onRowDown} className="ss-resize-row" role="separator" />
    </div>
  )
}
