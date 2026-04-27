import { useEffect, useMemo, useRef, useState } from 'react'

interface OdometerValueProps {
  value: number | null | undefined
  decimals?: number
  prefix?: string
  suffix?: string
  fallback?: string
  durationMs?: number
  className?: string
}

function clamp(num: number, min: number, max: number) {
  return Math.min(max, Math.max(min, num))
}

export function OdometerValue({
  value,
  decimals = 0,
  prefix = '',
  suffix = '',
  fallback = '—',
  durationMs = 420,
  className,
}: OdometerValueProps) {
  const numericValue = typeof value === 'number' && Number.isFinite(value) ? value : null
  const [display, setDisplay] = useState<number | null>(numericValue)
  const previousRef = useRef<number>(numericValue ?? 0)

  useEffect(() => {
    if (numericValue === null) {
      setDisplay(null)
      return
    }

    const start = previousRef.current
    const end = numericValue
    const delta = end - start
    if (Math.abs(delta) < Number.EPSILON) {
      setDisplay(end)
      previousRef.current = end
      return
    }

    let raf = 0
    const startedAt = performance.now()

    const tick = (now: number) => {
      const t = clamp((now - startedAt) / durationMs, 0, 1)
      // easeOutCubic for odometer/ticker-like deceleration.
      const eased = 1 - Math.pow(1 - t, 3)
      const current = start + delta * eased
      setDisplay(current)
      if (t < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        previousRef.current = end
      }
    }

    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [durationMs, numericValue])

  const text = useMemo(() => {
    if (display === null) return fallback
    return `${prefix}${display.toFixed(decimals)}${suffix}`
  }, [decimals, display, fallback, prefix, suffix])

  return <span className={className}>{text}</span>
}
