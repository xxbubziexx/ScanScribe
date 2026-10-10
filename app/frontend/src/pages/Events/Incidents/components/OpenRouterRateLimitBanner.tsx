import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { eventsApi } from '@/lib/events'
import { formatCountdown } from '../utils/incidentFormatters'

export function OpenRouterRateLimitBanner() {
  const rateLimitQuery = useQuery({
    queryKey: ['events-rate-limit-status'],
    queryFn: () => eventsApi.rateLimitStatus(),
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  const [remainingSec, setRemainingSec] = useState<number>(0)

  useEffect(() => {
    const status = rateLimitQuery.data
    if (!status?.is_rate_limited) {
      setRemainingSec(0)
      return
    }

    const initSec =
      status.seconds_remaining != null && status.seconds_remaining > 0
        ? Math.max(0, Math.ceil(status.seconds_remaining))
        : status.cooldown_until
          ? Math.max(0, Math.ceil(status.cooldown_until - Date.now() / 1000))
          : 0

    setRemainingSec(initSec)

    const timer = setInterval(() => {
      setRemainingSec((prev) => {
        if (prev <= 1) {
          void rateLimitQuery.refetch()
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [rateLimitQuery.data])

  const status = rateLimitQuery.data
  if (!status?.is_rate_limited) {
    return null
  }

  const resetDate = status.cooldown_until ? new Date(status.cooldown_until * 1000) : null
  const localResetTime = resetDate
    ? resetDate.toLocaleTimeString([], {
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        timeZoneName: 'short',
      })
    : ''
  const utcResetTime = status.reset_time_formatted ? status.reset_time_formatted : ''

  return (
    <div className="ss-rate-limit-banner">
      <div className="ss-rate-limit-banner__main">
        <div className="ss-rate-limit-banner__left">
          <div className="ss-rate-limit-badge">
            <span className="ss-rate-limit-pulse"></span>
            <span>
              {status.is_paused_waiting_start ? 'EVENTS ROUTING PAUSED' : 'OPENROUTER RATE LIMIT'}
            </span>
          </div>
          <div className="ss-rate-limit-timer">
            <span className="ss-rate-limit-timer__label">
              {status.is_paused_waiting_start
                ? 'AUTO-START DISABLED'
                : remainingSec > 0
                  ? 'RESETS IN'
                  : 'COOLDOWN'}
            </span>
            <span className="ss-rate-limit-timer__clock">
              {status.is_paused_waiting_start
                ? 'RESTART REQUIRED'
                : remainingSec > 0
                  ? `T-${formatCountdown(remainingSec)}`
                  : 'COOLDOWN EXPIRED'}
            </span>
          </div>
        </div>

        <div className="ss-rate-limit-banner__info">
          <div className="ss-rate-limit-target">
            <span>⏱️ Target Reset Time:</span>
            <strong className="text-amber-200">{localResetTime || utcResetTime}</strong>
            {localResetTime && utcResetTime && (
              <span className="text-amber-400/70 text-xs font-mono">({utcResetTime})</span>
            )}
          </div>
          <p className="ss-rate-limit-reason" title={status.reason || undefined}>
            {status.reason ||
              'Rate limit cooldown active. Events pipeline LLM routing is paused to prevent wasted requests.'}
          </p>
        </div>

        <div className="ss-rate-limit-banner__actions">
          <button
            type="button"
            className="ss-btn-ghost text-xs py-1.5 px-3 flex items-center gap-1 shrink-0"
            onClick={() => void rateLimitQuery.refetch()}
            disabled={rateLimitQuery.isFetching}
            title="Check if rate limit has expired"
          >
            <span>🔄</span> {rateLimitQuery.isFetching ? 'Checking…' : 'Check Now'}
          </button>
        </div>
      </div>
    </div>
  )
}
